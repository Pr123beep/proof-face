import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import solc from 'solc';
import { Contract, ContractFactory, JsonRpcProvider } from 'ethers';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const contractFile = path.join(here, 'contracts', 'EvidenceRegistry.sol');
const hardhatCli = path.join(root, 'node_modules', 'hardhat', 'dist', 'src', 'cli.js');
const rpcPort = Number(process.env.CHAIN_RPC_PORT || 8545);
const apiPort = Number(process.env.CHAIN_API_PORT || 8546);
const rpcUrl = `http://127.0.0.1:${rpcPort}`;

function json(res, status, value) {
  const body = JSON.stringify(value);
  res.writeHead(status, {
    'content-type': 'application/json',
    'content-length': Buffer.byteLength(body),
    'access-control-allow-origin': '*',
  });
  res.end(body);
}

async function readBody(req) {
  let body = '';
  for await (const chunk of req) {
    body += chunk;
    if (body.length > 1_000_000) throw new Error('request body too large');
  }
  return body ? JSON.parse(body) : {};
}

function assertHash(name, value) {
  if (!/^0x[0-9a-fA-F]{64}$/.test(value || '')) {
    throw new Error(`${name} must be a 32-byte 0x-prefixed hash`);
  }
}

async function compileContract() {
  const source = await readFile(contractFile, 'utf8');
  const input = {
    language: 'Solidity',
    sources: { 'EvidenceRegistry.sol': { content: source } },
    settings: {
      evmVersion: 'paris',
      optimizer: { enabled: true, runs: 200 },
      outputSelection: { '*': { '*': ['abi', 'evm.bytecode'] } },
    },
  };
  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  const errors = (output.errors || []).filter((item) => item.severity === 'error');
  if (errors.length) throw new Error(errors.map((item) => item.formattedMessage).join('\n'));
  const artifact = output.contracts['EvidenceRegistry.sol'].EvidenceRegistry;
  return { abi: artifact.abi, bytecode: `0x${artifact.evm.bytecode.object}` };
}

async function waitForRpc(child, stderr) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Hardhat Network exited early. ${stderr.value}`);
    try {
      const response = await fetch(rpcUrl, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'eth_chainId', params: [] }),
      });
      const payload = await response.json();
      if (payload.result === '0x7a69') return;
    } catch { /* retry during startup */ }
    await delay(150);
  }
  throw new Error(`Hardhat Network did not start in time. ${stderr.value}`);
}

async function start() {
  const stderr = { value: '' };
  const hardhat = spawn(process.execPath, [
    hardhatCli,
    'node',
    '--hostname', '127.0.0.1',
    '--port', String(rpcPort),
    '--chain-id', '31337',
  ], {
    cwd: root,
    env: { ...process.env, CI: 'true', HARDHAT_DISABLE_TELEMETRY_PROMPT: 'true' },
    stdio: ['ignore', 'ignore', 'pipe'],
  });
  hardhat.stderr.on('data', (chunk) => { stderr.value = `${stderr.value}${chunk}`.slice(-4000); });
  await waitForRpc(hardhat, stderr);

  const provider = new JsonRpcProvider(rpcUrl);
  const signer = await provider.getSigner(0);
  const artifact = await compileContract();
  const factory = new ContractFactory(artifact.abi, artifact.bytecode, signer);
  const deployed = await factory.deploy();
  await deployed.waitForDeployment();
  const address = await deployed.getAddress();
  const contract = new Contract(address, artifact.abi, signer);

  const api = createServer(async (req, res) => {
    if (req.method === 'OPTIONS') {
      res.writeHead(204, { 'access-control-allow-origin': '*', 'access-control-allow-methods': 'GET,POST,OPTIONS', 'access-control-allow-headers': 'content-type' });
      return res.end();
    }

    try {
      if (req.method === 'GET' && req.url === '/health') {
        const blockNumber = await provider.getBlockNumber();
        return json(res, 200, { ok: true, chainId: 31337, blockNumber, contractAddress: address, rpcUrl, engine: 'Hardhat Network 3' });
      }

      if (req.method === 'POST' && req.url === '/record') {
        const { evidenceHash, sourceHash, sourceUrl } = await readBody(req);
        assertHash('evidenceHash', evidenceHash);
        assertHash('sourceHash', sourceHash);
        if (typeof sourceUrl !== 'string' || !sourceUrl.startsWith('http')) throw new Error('sourceUrl must be an http(s) URL');

        const existing = await contract.getEvidence(evidenceHash);
        let receipt = null;
        const reused = existing[2] > 0n;
        if (!reused) {
          const tx = await contract.anchor(evidenceHash, sourceHash, sourceUrl);
          receipt = await tx.wait();
        }
        const stored = await contract.getEvidence(evidenceHash);
        const verified = await contract.verify(evidenceHash, sourceHash, sourceUrl);
        return json(res, 200, {
          recorded: true,
          reused,
          verified,
          chainId: 31337,
          network: 'ProofFace Hardhat EVM',
          contractAddress: address,
          transactionHash: receipt?.hash || null,
          blockNumber: receipt?.blockNumber || null,
          blockHash: receipt?.blockHash || null,
          submitter: stored[3],
          anchoredAt: Number(stored[2]),
          evidenceHash,
          sourceHash,
          sourceUrl,
        });
      }

      if (req.method === 'POST' && req.url === '/verify') {
        const { evidenceHash, sourceHash, sourceUrl } = await readBody(req);
        assertHash('evidenceHash', evidenceHash);
        assertHash('sourceHash', sourceHash);
        const stored = await contract.getEvidence(evidenceHash);
        const exists = stored[2] > 0n;
        const matches = exists && await contract.verify(evidenceHash, sourceHash, sourceUrl);
        return json(res, 200, {
          exists,
          matches,
          chainId: 31337,
          network: 'ProofFace Hardhat EVM',
          contractAddress: address,
          anchoredAt: Number(stored[2]),
          storedSourceHash: stored[0],
          storedSourceUrl: stored[1],
          submitter: stored[3],
        });
      }

      return json(res, 404, { error: 'not found' });
    } catch (error) {
      return json(res, 400, { error: error instanceof Error ? error.message : String(error) });
    }
  });

  api.listen(apiPort, '127.0.0.1', () => {
    console.log(`ProofFace chain ready · Hardhat EVM 31337 · contract ${address} · API http://127.0.0.1:${apiPort}`);
  });

  let closing = false;
  const shutdown = () => {
    if (closing) return;
    closing = true;
    api.close();
    hardhat.kill('SIGTERM');
    setTimeout(() => { if (hardhat.exitCode === null) hardhat.kill('SIGKILL'); }, 1500).unref();
  };
  hardhat.on('exit', (code) => {
    if (!closing) {
      console.error(`Hardhat Network stopped unexpectedly with code ${code}. ${stderr.value}`);
      process.exit(1);
    }
    process.exit(0);
  });
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

start().catch((error) => {
  console.error(error);
  process.exit(1);
});

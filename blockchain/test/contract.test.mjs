import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import solc from 'solc';

test('EvidenceRegistry compiles and exposes anchor + verify', async () => {
  const source = await readFile(path.resolve('blockchain/contracts/EvidenceRegistry.sol'), 'utf8');
  const output = JSON.parse(solc.compile(JSON.stringify({
    language: 'Solidity',
    sources: { 'EvidenceRegistry.sol': { content: source } },
    settings: { evmVersion: 'paris', outputSelection: { '*': { '*': ['abi', 'evm.bytecode'] } } },
  })));
  const errors = (output.errors || []).filter((item) => item.severity === 'error');
  assert.equal(errors.length, 0, errors.map((item) => item.formattedMessage).join('\n'));
  const artifact = output.contracts['EvidenceRegistry.sol'].EvidenceRegistry;
  const names = artifact.abi.filter((item) => item.type === 'function').map((item) => item.name);
  assert.deepEqual(names.sort(), ['anchor', 'getEvidence', 'verify']);
  assert.ok(artifact.evm.bytecode.object.length > 100);
});

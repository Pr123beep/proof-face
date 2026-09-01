import { defineConfig } from 'hardhat/config';

export default defineConfig({
  solidity: {
    version: '0.8.36',
    settings: {
      evmVersion: 'paris',
      optimizer: { enabled: true, runs: 200 },
    },
  },
  networks: {
    hardhatMainnet: {
      type: 'edr-simulated',
      chainType: 'l1',
      chainId: 31337,
    },
  },
});

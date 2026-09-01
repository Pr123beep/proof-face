# ProofFace local EVM

`EvidenceRegistry.sol` stores the evidence hash, source-content hash, discovered post URL, timestamp, and submitter on an Ethereum-compatible Hardhat Network 3 chain (chain ID `31337`). The chain service starts the EVM, compiles and deploys the contract, submits transactions, waits for receipts, and calls the contract's `verify` view function against the original data.

Chain state lasts for the running demo session and starts clean on the next launch. The contract address is printed at startup and exposed through `/health`.

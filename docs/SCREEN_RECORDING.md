# Unedited screen-recording runbook

Use a photo that you own, is clear and front-facing, and already appears in a public social-media post. Confirm the post is visible while signed out before recording.

## Before recording

1. Add the restricted Google Vision key to `.env`.
2. Run `npm run dev:all` and wait until CHAIN, API, and WEB are ready.
3. In another terminal, run `./scripts/record-demo.sh`.
4. Keep the source post URL available only if you want to compare it after ProofFace discovers it; do not paste or configure the URL in ProofFace.
5. Close unrelated windows and hide secrets. Never show `.env` on screen.

## Record in one take

1. Show the clean terminal with `npm run dev:all` running and the chain contract address visible.
2. Open `http://localhost:3000` and point out **SEARCH READY** and **LOCAL EVM / CHAIN 31337**.
3. Upload the published portrait. Do not show or enter the expected post URL.
4. Click **Run verification** and keep the live pipeline visible:
   - YuNet + SFace encoding
   - reverse-image search
   - social-post match
   - chain seal
   - contract read-back
5. On the result screen, open the discovered post with the arrow and show that it is a real matching social post.
6. Return to ProofFace and show the annotated face, model, 128D vector, and match signals.
7. Show the **Ledger** tab: chain ID, block, contract, transaction, and evidence hashes.
8. Click **Run verification again** and show the successful exact match.
9. Click **Demonstrate rejection of modified evidence** and show that the tamper test passes because altered data is rejected.
10. End on the Overview with the discovered post and mined transaction visible.

## Submission check

- The recording is unedited and includes the whole run.
- The shared video link works in an incognito window.
- The GitHub repository contains the source, README, `.env.example`, contract, tests, and this runbook.
- No API key, private image, or biometric data is committed.
- Submit only after testing the exact GitHub and video links.

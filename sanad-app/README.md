# SANAD — bitchat for medicine

**The guiding principle (owner, 2026-08-04):** SANAD is an app that works and
runs purely for medical cases and helps doctors and patients talk to each
other worldwide to solve medical issues — with or without internet, war zone
first. That is the problem this app exists to solve. Nothing ships that does
not serve it.

SANAD is built on the design bitchat proved (Jack Dorsey's open-source,
public-domain Bluetooth mesh messenger, July 2025) — but where bitchat is
chat rooms, SANAD is a **triage board**: the unit is the de-identified
clinical case, not the message.

## Architecture

- **One packet format everywhere.** Every action (case, claim, reply, order,
  outcome) is an append-only event with a random id, serialized as
  `SND1.<base64url(JSON)>`, one per line — byte-identical to the packets of
  the web board at https://timesofpalestine.com/sanad/. The app and the page
  import each other's packets and merge idempotently: importing the same
  packet twice changes nothing.
- **Carriers, not a network.** v0.1 moves packets over the OS share sheet
  (any messaging app, AirDrop/Quick Share, bitchat itself) and paste-import.
  The Bluetooth mesh (ported from bitchat-android) is the next milestone —
  see the roadmap.
- **State is derived.** The board replays the event log; order of arrival
  never matters.

## Rules (charter-bound)

- No names, no ID numbers, no faces in any packet — ever.
- Not a medical service and not an emergency line; the app says so on its
  own screens.
- Trust is professional referral (owner decision 2026-08-04): doctors who
  know each other and vouch for each other. No verification gate.
- A missing key or feature must never block advice — care outranks secrecy.

## Building

CI builds a debug APK on every push/PR touching `sanad-app/`
(`.github/workflows/sanad-app.yml`); grab it from the workflow artifacts.
Locally: `cd sanad-app && gradle assembleDebug` (Java 17, Android SDK 34).

## Roadmap (tracked in repo issue #149)

1. **v0.1 (this code):** native case board — post, triage-sort, claim,
   reply, share/import SND1 packets interoperable with the web board.
2. **v0.2:** end-to-end sealed reply threads (same ECDH P-256 + AES-GCM
   scheme as the web board, via Android Keystore), Arabic UI first-class.
3. **v0.3:** the bitchat mesh, ported from `permissionlesstech/
   bitchat-android` (public domain): BLE central+peripheral, 7-hop relay,
   store-and-forward — plus the web board's GATT bridge contract
   (service `f0a1d000-1e5a-4d0e-9a2b-000000000001`) so any phone running
   SANAD is also the bridge for any phone running the web page.
4. **v1.0:** Nostr fallback for worldwide reach when any internet exists,
   patient-facing mode, F-Droid/APK distribution page on the site.

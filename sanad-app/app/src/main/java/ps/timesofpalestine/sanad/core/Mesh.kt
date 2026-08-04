package ps.timesofpalestine.sanad.core

/**
 * The mesh contract. v0.1 ships constants only — the BLE mesh itself is the
 * v0.3 milestone, ported from permissionlesstech/bitchat-android (public
 * domain): central+peripheral dual role, 7-hop TTL relay, store-and-forward.
 *
 * These UUIDs are the web board's published bridge contract: a SANAD phone
 * advertising this service IS the bridge for any phone running the web page
 * at timesofpalestine.com/sanad/ — the page writes packets to INBOX in
 * 180-byte chunks and subscribes to OUTBOX.
 */
object Mesh {
    const val SERVICE = "f0a1d000-1e5a-4d0e-9a2b-000000000001"
    const val INBOX = "f0a1d000-1e5a-4d0e-9a2b-000000000002"   // page → app
    const val OUTBOX = "f0a1d000-1e5a-4d0e-9a2b-000000000003"  // app → page
    const val CHUNK = 180
    const val CHANNEL = "#sanad"   // the meeting point on the bitchat mesh
}

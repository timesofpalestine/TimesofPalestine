package ps.timesofpalestine.sanad.core

import android.content.SharedPreferences
import android.util.Base64
import org.json.JSONObject
import java.math.BigInteger
import java.security.KeyFactory
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.PrivateKey
import java.security.PublicKey
import java.security.SecureRandom
import java.security.interfaces.ECPublicKey
import java.security.spec.ECGenParameterSpec
import java.security.spec.ECParameterSpec
import java.security.spec.ECPoint
import java.security.spec.ECPublicKeySpec
import java.security.spec.PKCS8EncodedKeySpec
import java.security.spec.X509EncodedKeySpec
import javax.crypto.Cipher
import javax.crypto.KeyAgreement
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * Interop with the web board's sealed threads. The page uses WebCrypto:
 * ECDH over P-256, the raw shared secret (the X coordinate, 32 bytes) used
 * directly as an AES-256-GCM key, 12-byte IV, tag appended to the
 * ciphertext, all base64url. Android's platform crypto speaks exactly the
 * same primitives, so a reply sealed on a phone opens in the browser and
 * vice versa — no third-party cipher code on either side.
 */
object Crypto {
    private const val B64 = Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING
    private fun enc(b: ByteArray): String = Base64.encodeToString(b, B64)
    private fun dec(s: String): ByteArray = Base64.decode(s, B64)

    private val P256: ECParameterSpec by lazy {
        val g = KeyPairGenerator.getInstance("EC")
        g.initialize(ECGenParameterSpec("secp256r1"))
        (g.generateKeyPair().public as ECPublicKey).params
    }

    /** Load-or-mint the device keypair, persisted like the page's localStorage keys. */
    fun keys(prefs: SharedPreferences): KeyPair {
        val priv = prefs.getString("key.priv", null)
        val pub = prefs.getString("key.pub", null)
        if (priv != null && pub != null) {
            val kf = KeyFactory.getInstance("EC")
            return KeyPair(
                kf.generatePublic(X509EncodedKeySpec(dec(pub))),
                kf.generatePrivate(PKCS8EncodedKeySpec(dec(priv))))
        }
        val g = KeyPairGenerator.getInstance("EC")
        g.initialize(ECGenParameterSpec("secp256r1"))
        val kp = g.generateKeyPair()
        prefs.edit()
            .putString("key.priv", enc(kp.private.encoded))
            .putString("key.pub", enc(kp.public.encoded))
            .apply()
        return kp
    }

    private fun fixed32(i: BigInteger): ByteArray {
        val raw = i.toByteArray()
        val out = ByteArray(32)
        if (raw.size >= 32) System.arraycopy(raw, raw.size - 32, out, 0, 32)
        else System.arraycopy(raw, 0, out, 32 - raw.size, raw.size)
        return out
    }

    /** The slim JWK the page attaches to events: {kty, crv, x, y}. */
    fun jwk(pub: PublicKey): JSONObject {
        val p = (pub as ECPublicKey).w
        return JSONObject().put("kty", "EC").put("crv", "P-256")
            .put("x", enc(fixed32(p.affineX))).put("y", enc(fixed32(p.affineY)))
    }

    fun fromJwk(j: JSONObject?): PublicKey? {
        if (j == null) return null
        return try {
            val x = BigInteger(1, dec(j.getString("x")))
            val y = BigInteger(1, dec(j.getString("y")))
            KeyFactory.getInstance("EC")
                .generatePublic(ECPublicKeySpec(ECPoint(x, y), P256))
        } catch (_: Exception) { null }
    }

    fun samePk(a: JSONObject?, b: JSONObject?): Boolean =
        a != null && b != null &&
        a.optString("x") == b.optString("x") && a.optString("y") == b.optString("y")

    private fun shared(priv: PrivateKey, their: PublicKey): ByteArray {
        val ka = KeyAgreement.getInstance("ECDH")
        ka.init(priv); ka.doPhase(their, true)
        return ka.generateSecret()   // raw X coordinate — WebCrypto's derived key bytes
    }

    /** Seal text to a counterpart public key -> {"iv": b64u, "ct": b64u}. */
    fun seal(text: String, priv: PrivateKey, theirJwk: JSONObject?): JSONObject? {
        val their = fromJwk(theirJwk) ?: return null
        return try {
            val iv = ByteArray(12).also { SecureRandom().nextBytes(it) }
            val c = Cipher.getInstance("AES/GCM/NoPadding")
            c.init(Cipher.ENCRYPT_MODE,
                SecretKeySpec(shared(priv, their), "AES"), GCMParameterSpec(128, iv))
            JSONObject().put("iv", enc(iv))
                .put("ct", enc(c.doFinal(text.toByteArray(Charsets.UTF_8))))
        } catch (_: Exception) { null }
    }

    /** Open a sealed box from a counterpart public key, or null. */
    fun open(box: JSONObject?, priv: PrivateKey, theirJwk: JSONObject?): String? {
        if (box == null) return null
        val their = fromJwk(theirJwk) ?: return null
        return try {
            val c = Cipher.getInstance("AES/GCM/NoPadding")
            c.init(Cipher.DECRYPT_MODE,
                SecretKeySpec(shared(priv, their), "AES"),
                GCMParameterSpec(128, dec(box.getString("iv"))))
            String(c.doFinal(dec(box.getString("ct"))), Charsets.UTF_8)
        } catch (_: Exception) { null }
    }
}

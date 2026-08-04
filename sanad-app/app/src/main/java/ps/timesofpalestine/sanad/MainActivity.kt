package ps.timesofpalestine.sanad

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import ps.timesofpalestine.sanad.core.Board
import ps.timesofpalestine.sanad.core.Crypto
import ps.timesofpalestine.sanad.core.Mesh
import ps.timesofpalestine.sanad.core.Snd1
import java.security.KeyPair
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * SANAD v0.2 — bitchat for medicine.
 * New in this stage: native decryption of the web board's sealed threads
 * (ECDH P-256 + AES-GCM via platform crypto — a reply sealed in a browser
 * opens here, and vice versa), a first-class Arabic RTL interface, and the
 * patient role from the north star: doctors AND patients, worldwide.
 */
class MainActivity : Activity() {

    private val specialties = listOf(
        "General surgery", "Orthopaedics / trauma", "Plastics & burns", "Vascular",
        "Neurosurgery", "Paediatrics", "Paediatric surgery", "Obstetrics",
        "Anaesthesia / ICU", "Infectious disease", "Wound & stoma care",
        "Nephrology / dialysis", "Ophthalmology", "Maxillofacial", "Radiology",
        "Internal medicine", "Nutrition", "Mental health", "Physiotherapy / rehab")
    private val zones = listOf("North Gaza", "Gaza City", "Deir al-Balah",
        "Khan Younis", "Rafah", "West Bank", "Displaced / outside", "Worldwide")
    private val urgencies = listOf("red", "amber", "routine")
    private val roles = listOf("field", "specialist", "patient")

    private val STR: Map<String, Map<String, String>> = mapOf(
        "en" to mapOf(
            "tag" to "cases only · works without internet · not a medical service",
            "new" to "＋ New case", "carrier" to "Carrier ⇅", "back" to "Back",
            "empty" to ("No cases on this device yet. Post one, or import packets " +
                "from a colleague — bitchat channel ${Mesh.CHANNEL}, WhatsApp, or " +
                "the web board at timesofpalestine.com/sanad/."),
            "reply" to "Reply", "claim" to "Claim", "claimedBy" to "Claimed by",
            "locked" to "🔒 encrypted for the case participants",
            "newT" to "New case",
            "newSub" to "Plain words. No names, no ID numbers, no faces. One clear question.",
            "role" to "You are", "roleField" to "Clinician",
            "roleSpec" to "Specialist", "rolePatient" to "Patient",
            "patientHint" to ("Patients are welcome here. Describe what is happening " +
                "in your own words — a doctor on the network answers. Never wait for " +
                "this board in an emergency."),
            "spec" to "Specialty", "urg" to "Urgency (red 1h · amber 6h · routine 48h)",
            "zone" to "Zone", "fac" to "Facility or medical point (optional for patients)",
            "age" to "Age band (e.g. adult 18–49, 5–11)", "sex" to "Sex (F / M / unknown)",
            "pres" to "What happened and what you see",
            "find" to "Findings, vitals, what you have done (leave blank if unsure)",
            "res" to "What you have and what you lack",
            "q" to "The one question you need answered",
            "contact" to "How the answering doctor reaches you (when the network returns)",
            "name" to "Your name or initials",
            "consent" to "The patient or guardian gave verbal consent to discuss this case.",
            "consentSelf" to "I am the patient (or guardian) and I consent to this case being discussed.",
            "deid" to "I removed names, ID numbers, dates of birth and faces.",
            "save" to "Save & queue", "both" to "Both boxes have to be ticked",
            "needPQ" to "Presentation and question are required",
            "carT" to "Carrier",
            "carSub" to ("One packet format, every path: share to bitchat (channel " +
                "${Mesh.CHANNEL}), WhatsApp, AirDrop/Quick Share — or paste packets " +
                "you received. Importing twice never duplicates. Replies between the " +
                "case's two participants travel sealed; relays cannot read them."),
            "shareNew" to "Share new", "shareAll" to "Share everything",
            "imp" to "Paste SND1 packets here", "impBtn" to "Import",
            "imported" to "imported", "noNew" to "no new packets",
            "nothing" to "nothing to send", "advice" to "Your advice / reply",
            "send" to "Send", "cancel" to "Cancel", "sealed" to "sealed 🔒"),
        "ar" to mapOf(
            "tag" to "للحالات الطبية فقط · تعمل بلا إنترنت · ليست خدمة طبية",
            "new" to "＋ حالة جديدة", "carrier" to "الناقل ⇅", "back" to "رجوع",
            "empty" to ("لا حالات على هذا الجهاز بعد. ارفع حالة، أو استورد حزماً من " +
                "زميل — قناة بيتشات ${Mesh.CHANNEL} أو واتساب أو لوحة الويب على " +
                "timesofpalestine.com/sanad/‏."),
            "reply" to "رد", "claim" to "تسلّم", "claimedBy" to "تسلّمها",
            "locked" to "🔒 مشفّرة لطرفي الحالة",
            "newT" to "حالة جديدة",
            "newSub" to "كلمات بسيطة. لا أسماء ولا أرقام هوية ولا وجوه. سؤال واحد واضح.",
            "role" to "أنت", "roleField" to "طبيب ميداني",
            "roleSpec" to "أخصائي", "rolePatient" to "مريض",
            "patientHint" to ("المرضى على الرحب هنا. صف ما يحدث بكلماتك، وسيجيبك طبيب " +
                "من الشبكة. لا تنتظر هذه اللوحة في الحالات الطارئة أبداً."),
            "spec" to "التخصص", "urg" to "الاستعجال (أحمر ساعة · برتقالي ٦ · عادي ٤٨)",
            "zone" to "المنطقة", "fac" to "المرفق أو النقطة الطبية (اختياري للمرضى)",
            "age" to "الفئة العمرية (مثال: بالغ ١٨–٤٩، ٥–١١)", "sex" to "الجنس (أنثى/ذكر/غير معروف)",
            "pres" to "ماذا حدث وماذا ترى",
            "find" to "الفحص والعلامات وما فعلته (اتركه فارغاً إن لم تعرف)",
            "res" to "ما يتوفر وما ينقص",
            "q" to "السؤال الواحد الذي تحتاج إجابته",
            "contact" to "كيف يصل إليك الطبيب المجيب (عند عودة الشبكة)",
            "name" to "الاسم أو الأحرف الأولى",
            "consent" to "أعطى المريض أو وليّه موافقة شفهية على مناقشة الحالة.",
            "consentSelf" to "أنا المريض (أو وليّه) وأوافق على مناقشة هذه الحالة.",
            "deid" to "أزلت الأسماء وأرقام الهوية وتواريخ الميلاد والوجوه.",
            "save" to "احفظ وأدرج", "both" to "لا بد من تعليم الخانتين",
            "needPQ" to "الوصف والسؤال مطلوبان",
            "carT" to "الناقل",
            "carSub" to ("صيغة واحدة للحزمة وكل الطرق: شارك إلى بيتشات (قناة " +
                "${Mesh.CHANNEL}) أو واتساب أو AirDrop/Quick Share — أو الصق حزماً " +
                "استلمتها. الاستيراد مرتين لا يكرر شيئاً. والردود بين طرفي الحالة " +
                "تنتقل مشفّرة ولا يقرؤها الوسطاء."),
            "shareNew" to "شارك الجديد", "shareAll" to "شارك كل شيء",
            "imp" to "الصق حزم SND1 هنا", "impBtn" to "استيراد",
            "imported" to "استُوردت", "noNew" to "لا حزم جديدة",
            "nothing" to "لا شيء للإرسال", "advice" to "مشورتك / ردك",
            "send" to "إرسال", "cancel" to "إلغاء", "sealed" to "مشفّرة 🔒"))

    private lateinit var root: LinearLayout
    private lateinit var kp: KeyPair
    private var lang = "en"
    private fun s(k: String): String = STR[lang]!![k] ?: k
    private fun prefs() = getSharedPreferences("sanad", MODE_PRIVATE)

    private fun log(): JSONArray = JSONArray(prefs().getString("events", "[]"))
    private fun saveLog(a: JSONArray) { prefs().edit().putString("events", a.toString()).apply() }
    private fun sent(): MutableSet<String> =
        prefs().getStringSet("sent", emptySet())!!.toMutableSet()
    private fun saveSent(v: Set<String>) { prefs().edit().putStringSet("sent", v).apply() }
    private fun myRole(): String = prefs().getString("role", "field")!!

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        lang = prefs().getString("lang", "en")!!
        kp = Crypto.keys(prefs())
        val scroll = ScrollView(this)
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val pad = dp(14); setPadding(pad, pad, pad, dp(40))
        }
        scroll.addView(root)
        setContentView(scroll)
        applyDirection()
        handleShared(intent)
        renderBoard()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleShared(intent)
        renderBoard()
    }

    private fun applyDirection() {
        window.decorView.layoutDirection =
            if (lang == "ar") View.LAYOUT_DIRECTION_RTL else View.LAYOUT_DIRECTION_LTR
    }

    private fun handleShared(i: Intent?) {
        val text = i?.getStringExtra(Intent.EXTRA_TEXT) ?: return
        val events = Snd1.decode(text)
        if (events.isEmpty()) return
        val a = log(); val n = Board.merge(a, events); saveLog(a)
        if (n > 0) toast("+$n")
    }

    // ---------------- chrome ----------------

    private fun chrome(title: String, sub: String) {
        val bar = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
        bar.addView(TextView(this).apply {
            text = title; textSize = 26f; setTypeface(null, Typeface.BOLD)
            layoutParams = LinearLayout.LayoutParams(0,
                LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        })
        bar.addView(smallButton(if (lang == "ar") "EN" else "ع") {
            lang = if (lang == "ar") "en" else "ar"
            prefs().edit().putString("lang", lang).apply()
            applyDirection(); renderBoard()
        })
        root.addView(bar)
        root.addView(small(sub))
    }

    // ---------------- board ----------------

    private fun renderBoard() {
        root.removeAllViews()
        chrome("SANAD · سند", s("tag"))
        rowButtons(s("new") to { renderForm() }, s("carrier") to { renderCarrier() })

        val cases = Board.derive(jsonList(log()))
        if (cases.isEmpty()) { para(s("empty")); return }
        val df = SimpleDateFormat("MM-dd HH:mm", Locale.US)
        val myJwk = Crypto.jwk(kp.public)
        for (c in cases) {
            val box = card(when (c.urgency) { "red" -> 0xFFA61B2B.toInt()
                "routine" -> 0xFF1F5E52.toInt() else -> 0xFFA8720F.toInt() })
            box.addView(bold("${c.ref} · ${c.specialty} · ${c.urgency.uppercase()} · ${c.status.uppercase()}"))
            box.addView(small("${c.ageBand} · ${c.sex} · ${c.zone} · ${c.facility} · ${df.format(Date(c.createdAt))}"))
            box.addView(bold("Q: ${c.question}"))
            box.addView(small(c.presentation))
            if (c.claimBy != null) box.addView(small("${s("claimedBy")} ${c.claimBy}"))
            for (m in c.thread) {
                val who = m.optJSONObject("by")?.optString("n") ?: "?"
                val enc = m.optJSONObject("enc")
                val body = if (enc != null) {
                    val their = counterpartFor(c, m.optJSONObject("pk"), myJwk)
                    Crypto.open(enc, kp.private, their)?.let { "🔓 $it" } ?: s("locked")
                } else m.optString("text")
                box.addView(small("↳ $who: $body"))
            }
            val actions = LinearLayout(this)
            actions.addView(smallButton(s("reply")) { replyDialog(c.id) })
            if (myRole() != "patient" && c.status == "open")
                actions.addView(smallButton(s("claim")) {
                    emit(JSONObject().put("ty", "claim").put("cid", c.id)) })
            box.addView(actions)
            root.addView(box)
        }
    }

    /** Which public key is the other end of this thread message? */
    private fun counterpartFor(c: ps.timesofpalestine.sanad.core.CaseView,
                               msgPk: JSONObject?, myJwk: JSONObject): JSONObject? {
        val mineIsSender = Crypto.samePk(msgPk, myJwk)
        return if (mineIsSender)
            (if (Crypto.samePk(c.pk, myJwk)) c.claimPk else c.pk)
        else msgPk
    }

    // ---------------- new case ----------------

    private fun renderForm() {
        root.removeAllViews()
        chrome(s("newT"), s("newSub"))

        root.addView(small(s("role")))
        val roleRow = LinearLayout(this)
        val labels = mapOf("field" to s("roleField"), "specialist" to s("roleSpec"),
                           "patient" to s("rolePatient"))
        for (r in roles) roleRow.addView(smallButton(
            (if (myRole() == r) "● " else "") + labels[r]!!) {
            prefs().edit().putString("role", r).apply(); renderForm() })
        root.addView(roleRow)
        if (myRole() == "patient") root.addView(small(s("patientHint")))

        val spec = spinner(specialties); labeled(s("spec"), spec)
        val urg = spinner(urgencies); labeled(s("urg"), urg); urg.setSelection(1)
        val zone = spinner(zones); labeled(s("zone"), zone)
        val fac = field(s("fac"))
        val age = field(s("age"))
        val sex = field(s("sex"))
        val pres = area(s("pres"))
        val find = area(s("find"))
        val res = area(s("res"))
        val q = area(s("q"))
        val contact = field(s("contact"))
        val name = field(s("name")).apply { setText(prefs().getString("me", "")) }
        val consent = CheckBox(this).apply {
            text = if (myRole() == "patient") s("consentSelf") else s("consent") }
        val deid = CheckBox(this).apply { text = s("deid") }
        root.addView(consent); root.addView(deid)
        rowButtons(
            s("save") to save@{
                if (!consent.isChecked || !deid.isChecked) { toast(s("both")); return@save }
                if (q.text.isBlank() || pres.text.isBlank()) { toast(s("needPQ")); return@save }
                prefs().edit().putString("me", name.text.toString().trim()).apply()
                val d = Date()
                val ref = "GZ-" + SimpleDateFormat("MMdd", Locale.US).format(d) +
                    "-A" + ((log().length() % 90) + 10)
                emit(JSONObject().put("ty", "case").put("ref", ref).put("c", JSONObject()
                    .put("specialty", spec.selectedItem.toString())
                    .put("urgency", urg.selectedItem.toString())
                    .put("ageBand", age.text.toString().trim())
                    .put("sex", sex.text.toString().trim())
                    .put("zone", zone.selectedItem.toString())
                    .put("facility", fac.text.toString().trim())
                    .put("presentation", pres.text.toString().trim())
                    .put("findings", find.text.toString().trim())
                    .put("resources", res.text.toString().trim())
                    .put("question", q.text.toString().trim())
                    .put("contact", contact.text.toString().trim())))
                shareUnsent()
            },
            s("back") to { renderBoard() })
    }

    // ---------------- carrier ----------------

    private fun renderCarrier() {
        root.removeAllViews()
        val unsentCount = jsonList(log()).count { !sent().contains(it.getString("id")) }
        chrome(s("carT"), s("carSub"))
        rowButtons(
            "${s("shareNew")} ($unsentCount)" to { shareUnsent() },
            s("shareAll") to { share(jsonList(log())) })
        val imp = area(s("imp"))
        rowButtons(
            s("impBtn") to {
                val got = Snd1.decode(imp.text.toString())
                val a = log(); val n = Board.merge(a, got); saveLog(a)
                toast(if (n > 0) "${s("imported")} $n" else s("noNew"))
                renderBoard()
            },
            s("back") to { renderBoard() })
    }

    // ---------------- engine glue ----------------

    private fun emit(e: JSONObject) {
        e.put("id", Snd1.uid()).put("ts", System.currentTimeMillis())
        e.put("by", JSONObject()
            .put("n", prefs().getString("me", "").orEmpty().ifBlank { "anon" })
            .put("r", myRole()).put("c", ""))
        e.put("pk", Crypto.jwk(kp.public))
        val a = log(); a.put(e); saveLog(a)
        renderBoard()
    }

    private fun replyDialog(cid: String) {
        val input = EditText(this).apply { minLines = 3 }
        AlertDialog.Builder(this).setTitle(s("advice"))
            .setView(input)
            .setPositiveButton(s("send")) { _, _ ->
                val text = input.text.toString().trim()
                if (text.isEmpty()) return@setPositiveButton
                // Seal to the thread counterpart when both keys exist —
                // exactly the web board's rule; cleartext otherwise, because
                // a missing key must never block advice.
                val c = Board.derive(jsonList(log())).find { it.id == cid }
                val myJwk = Crypto.jwk(kp.public)
                val their = if (c != null)
                    (if (Crypto.samePk(c.pk, myJwk)) c.claimPk else c.pk) else null
                val box = if (their != null && !Crypto.samePk(their, myJwk))
                    Crypto.seal(text, kp.private, their) else null
                val ev = JSONObject().put("ty", "reply").put("cid", cid)
                if (box != null) { ev.put("enc", box); toast(s("sealed")) }
                else ev.put("text", text)
                emit(ev)
            }
            .setNegativeButton(s("cancel"), null).show()
    }

    private fun shareUnsent() {
        val all = jsonList(log()); val done = sent()
        val q = all.filter { !done.contains(it.getString("id")) }
        if (q.isEmpty()) { toast(s("nothing")); renderBoard(); return }
        share(q)
    }

    private fun share(events: List<JSONObject>) {
        val text = Snd1.encode(events)
        val done = sent(); events.forEach { done.add(it.getString("id")) }; saveSent(done)
        startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"; putExtra(Intent.EXTRA_TEXT, text)
        }, "SANAD"))
        renderBoard()
    }

    private fun jsonList(a: JSONArray): List<JSONObject> =
        (0 until a.length()).map { a.getJSONObject(it) }

    // ---------------- tiny view helpers ----------------

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()
    private fun toast(m: String) = Toast.makeText(this, m, Toast.LENGTH_SHORT).show()
    private fun para(t: String) { root.addView(TextView(this).apply { text = t; setPadding(0, dp(10), 0, 0) }) }
    private fun bold(t: String) = TextView(this).apply { text = t; setTypeface(null, Typeface.BOLD) }
    private fun small(t: String) = TextView(this).apply { text = t; textSize = 13f; alpha = 0.8f }
    private fun field(hint: String): EditText {
        val e = EditText(this).apply { this.hint = hint; inputType = InputType.TYPE_CLASS_TEXT }
        root.addView(e); return e
    }
    private fun area(hint: String): EditText {
        val e = EditText(this).apply {
            this.hint = hint; minLines = 2
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
        }
        root.addView(e); return e
    }
    private fun spinner(items: List<String>): Spinner = Spinner(this).apply {
        adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, items)
    }
    private fun labeled(label: String, v: View) { root.addView(small(label)); root.addView(v) }
    private fun smallButton(label: String, onClick: () -> Unit): Button =
        Button(this).apply { text = label; setOnClickListener { onClick() } }
    private fun rowButtons(vararg items: Pair<String, () -> Unit>) {
        val row = LinearLayout(this).apply { gravity = Gravity.START }
        for ((label, fn) in items) row.addView(smallButton(label, fn))
        root.addView(row)
    }
    private fun card(edge: Int): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        val pad = dp(10); setPadding(pad, pad, pad, pad)
        setBackgroundColor(0x14000000)
        val lp = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT)
        lp.setMargins(0, dp(10), 0, 0); layoutParams = lp
        val stripe = View(this@MainActivity).apply {
            setBackgroundColor(edge)
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(4))
        }
        addView(stripe, 0)
    }
}

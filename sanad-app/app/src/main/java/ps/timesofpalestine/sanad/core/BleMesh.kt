package ps.timesofpalestine.sanad.core

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothGattServer
import android.bluetooth.BluetoothGattServerCallback
import android.bluetooth.BluetoothGattService
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.AdvertiseCallback
import android.bluetooth.le.AdvertiseData
import android.bluetooth.le.AdvertiseSettings
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import java.util.UUID
import java.util.ArrayDeque

/**
 * SANAD mesh v0.3 — bitchat's store-and-forward, rebuilt around the case.
 *
 * Every SANAD phone runs BOTH roles at once:
 *  - PERIPHERAL: advertises the published Sanad bridge service and serves a
 *    GATT server — which makes every SANAD phone the bridge for any browser
 *    running timesofpalestine.com/sanad/ (the page writes packets to INBOX
 *    in chunks and subscribes to OUTBOX), no extra hardware needed.
 *  - CENTRAL: scans for the same service on other SANAD phones and hardware
 *    bridges, pushes its own log, and subscribes to theirs.
 *
 * Multi-hop is store-and-forward: every device holds the full event log and
 * offers it at every encounter; merging is idempotent, so packets spread
 * device to device across a hospital or a camp exactly the way bitchat
 * relays messages — a case posted at one end reaches the other end through
 * whoever walked between them.
 */
@SuppressLint("MissingPermission")
class BleMesh(
    private val context: Context,
    /** Full newline-terminated SND1 packet text of everything this device holds. */
    private val allPackets: () -> String,
    /** Deliver received packet lines (complete lines only). */
    private val onPackets: (String) -> Unit,
    /** Short status strings for the UI. */
    private val onStatus: (String) -> Unit,
) {
    private val ui = Handler(Looper.getMainLooper())
    private val manager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
    private val adapter get() = manager.adapter

    private val SERVICE = UUID.fromString(Mesh.SERVICE)
    private val INBOX = UUID.fromString(Mesh.INBOX)
    private val OUTBOX = UUID.fromString(Mesh.OUTBOX)
    private val CCCD = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

    var running = false; private set
    var peers = 0; private set

    private var server: BluetoothGattServer? = null
    private var outboxChar: BluetoothGattCharacteristic? = null
    private val inBuffers = HashMap<String, StringBuilder>()   // per-device partial lines
    private val lastSync = HashMap<String, Long>()             // scan cooldown
    private val gatts = HashMap<String, BluetoothGatt>()

    // ---------------- lifecycle ----------------

    fun start() {
        if (running) return
        val a = adapter ?: return status("bluetooth unavailable")
        if (!a.isEnabled) return status("bluetooth is off")
        running = true
        startServer()
        startAdvertising()
        startScan()
        status("mesh on")
    }

    fun stop() {
        if (!running) return
        running = false
        try { adapter?.bluetoothLeAdvertiser?.stopAdvertising(advCb) } catch (_: Exception) {}
        try { adapter?.bluetoothLeScanner?.stopScan(scanCb) } catch (_: Exception) {}
        for (g in gatts.values) try { g.close() } catch (_: Exception) {}
        gatts.clear()
        try { server?.close() } catch (_: Exception) {}
        server = null; peers = 0
        status("mesh off")
    }

    private fun status(s: String) { ui.post { onStatus(s) } }
    private fun deliver(lines: String) { ui.post { onPackets(lines) } }

    private fun feed(key: String, chunk: ByteArray) {
        val buf = inBuffers.getOrPut(key) { StringBuilder() }
        buf.append(String(chunk, Charsets.UTF_8))
        val text = buf.toString()
        val cut = text.lastIndexOf('\n')
        if (cut >= 0) {
            deliver(text.substring(0, cut))
            buf.setLength(0); buf.append(text.substring(cut + 1))
        }
    }

    private fun chunks(text: String): List<ByteArray> {
        val bytes = (text + "\n").toByteArray(Charsets.UTF_8)
        val out = ArrayList<ByteArray>()
        var i = 0
        while (i < bytes.size) {
            val end = minOf(i + Mesh.CHUNK, bytes.size)
            out.add(bytes.copyOfRange(i, end)); i = end
        }
        return out
    }

    // ---------------- peripheral: the walking bridge ----------------

    private val serverCb = object : BluetoothGattServerCallback() {
        override fun onConnectionStateChange(device: BluetoothDevice, st: Int, newState: Int) {
            if (newState == BluetoothProfile.STATE_CONNECTED) { peers++; status("peer joined ($peers)") }
            else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                peers = maxOf(0, peers - 1); inBuffers.remove("s:" + device.address)
                status(if (peers > 0) "peers: $peers" else "listening")
            }
        }

        override fun onCharacteristicWriteRequest(
            device: BluetoothDevice, requestId: Int, ch: BluetoothGattCharacteristic,
            preparedWrite: Boolean, responseNeeded: Boolean, offset: Int, value: ByteArray?) {
            if (responseNeeded)
                server?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, value)
            if (ch.uuid == INBOX && value != null) feed("s:" + device.address, value)
        }

        override fun onDescriptorWriteRequest(
            device: BluetoothDevice, requestId: Int, descriptor: BluetoothGattDescriptor,
            preparedWrite: Boolean, responseNeeded: Boolean, offset: Int, value: ByteArray?) {
            if (responseNeeded)
                server?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, value)
            // A subscriber (the web page, or another SANAD phone) just enabled
            // notifications: hand over everything we hold, store-and-forward.
            if (descriptor.uuid == CCCD) Thread {
                try {
                    val ob = outboxChar ?: return@Thread
                    for (c in chunks(allPackets())) {
                        ob.value = c
                        server?.notifyCharacteristicChanged(device, ob, false)
                        Thread.sleep(35)
                    }
                } catch (_: Exception) {}
            }.start()
        }
    }

    private fun startServer() {
        try {
            server = manager.openGattServer(context, serverCb)
            val svc = BluetoothGattService(SERVICE, BluetoothGattService.SERVICE_TYPE_PRIMARY)
            val inbox = BluetoothGattCharacteristic(INBOX,
                BluetoothGattCharacteristic.PROPERTY_WRITE,
                BluetoothGattCharacteristic.PERMISSION_WRITE)
            val outbox = BluetoothGattCharacteristic(OUTBOX,
                BluetoothGattCharacteristic.PROPERTY_NOTIFY,
                BluetoothGattCharacteristic.PERMISSION_READ)
            outbox.addDescriptor(BluetoothGattDescriptor(CCCD,
                BluetoothGattDescriptor.PERMISSION_READ or BluetoothGattDescriptor.PERMISSION_WRITE))
            svc.addCharacteristic(inbox); svc.addCharacteristic(outbox)
            server?.addService(svc)
            outboxChar = outbox
        } catch (e: Exception) { status("server failed: ${e.message}") }
    }

    private val advCb = object : AdvertiseCallback() {
        override fun onStartFailure(errorCode: Int) { status("advertise failed ($errorCode)") }
        override fun onStartSuccess(settingsInEffect: AdvertiseSettings?) { status("listening") }
    }

    private fun startAdvertising() {
        try {
            adapter?.bluetoothLeAdvertiser?.startAdvertising(
                AdvertiseSettings.Builder()
                    .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_BALANCED)
                    .setConnectable(true).build(),
                AdvertiseData.Builder()
                    .addServiceUuid(ParcelUuid(SERVICE))
                    .setIncludeDeviceName(false).build(),
                advCb)
        } catch (e: Exception) { status("advertise failed: ${e.message}") }
    }

    // ---------------- central: find the others ----------------

    private val scanCb = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val addr = result.device.address ?: return
            val now = System.currentTimeMillis()
            if (now - (lastSync[addr] ?: 0) < 120_000) return   // resync every 2 min
            lastSync[addr] = now
            connect(result.device)
        }
    }

    private fun startScan() {
        try {
            adapter?.bluetoothLeScanner?.startScan(
                listOf(ScanFilter.Builder().setServiceUuid(ParcelUuid(SERVICE)).build()),
                ScanSettings.Builder()
                    .setScanMode(ScanSettings.SCAN_MODE_BALANCED).build(),
                scanCb)
        } catch (e: Exception) { status("scan failed: ${e.message}") }
    }

    private fun connect(device: BluetoothDevice) {
        try {
            val queue = ArrayDeque<ByteArray>()
            val cb = object : BluetoothGattCallback() {
                var inboxCh: BluetoothGattCharacteristic? = null

                override fun onConnectionStateChange(g: BluetoothGatt, st: Int, newState: Int) {
                    if (newState == BluetoothProfile.STATE_CONNECTED) g.requestMtu(247)
                    else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                        inBuffers.remove("c:" + g.device.address)
                        gatts.remove(g.device.address); try { g.close() } catch (_: Exception) {}
                    }
                }

                override fun onMtuChanged(g: BluetoothGatt, mtu: Int, st: Int) { g.discoverServices() }

                override fun onServicesDiscovered(g: BluetoothGatt, st: Int) {
                    val svc = g.getService(SERVICE) ?: return g.disconnect()
                    val theirOutbox = svc.getCharacteristic(OUTBOX)
                    inboxCh = svc.getCharacteristic(INBOX)
                    if (theirOutbox != null) {
                        g.setCharacteristicNotification(theirOutbox, true)
                        val d = theirOutbox.getDescriptor(CCCD)
                        if (d != null) {
                            d.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                            g.writeDescriptor(d)
                        }
                    }
                    status("syncing with a peer")
                }

                override fun onDescriptorWrite(g: BluetoothGatt, d: BluetoothGattDescriptor, st: Int) {
                    // Subscribed to their log — now push ours, one chunk per ack.
                    queue.addAll(chunks(allPackets()))
                    writeNext(g)
                }

                override fun onCharacteristicWrite(g: BluetoothGatt, c: BluetoothGattCharacteristic, st: Int) {
                    writeNext(g)
                }

                fun writeNext(g: BluetoothGatt) {
                    val ch = inboxCh ?: return
                    val next = queue.pollFirst() ?: return
                    try {
                        ch.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
                        ch.value = next
                        g.writeCharacteristic(ch)
                    } catch (_: Exception) {}
                }

                override fun onCharacteristicChanged(g: BluetoothGatt, c: BluetoothGattCharacteristic) {
                    if (c.uuid == OUTBOX) c.value?.let { feed("c:" + g.device.address, it) }
                }
            }
            gatts[device.address]?.let { try { it.close() } catch (_: Exception) {} }
            gatts[device.address] = device.connectGatt(context, false, cb)
        } catch (e: Exception) { status("connect failed: ${e.message}") }
    }
}

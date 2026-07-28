package com.shopmanager.materialuploader

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okio.BufferedSink
import okio.source
import org.json.JSONArray
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.util.UUID
import java.util.concurrent.TimeUnit

data class ComputerBinding(
    val desktopId: String,
    val desktopName: String,
    val accountId: String,
    val accountName: String,
    val host: String,
    val port: Int,
    val discoveryPort: Int,
    val token: String,
    val deviceId: String,
) {
    val key: String get() = "$desktopId/$accountId"
    val shortCode: String get() = desktopId.replace("-", "").take(8).uppercase()
}

data class MaterialSpec(val id: String, val name: String, val codes: List<String>, val hasMaterial: Boolean)
data class MaterialCategory(
    val id: String,
    val label: String,
    val color: String,
    val specs: List<MaterialSpec>,
    val needsMaterial: Boolean,
)
data class RemoteMaterialImage(val id: String, val name: String, val size: Long)

class ApiException(val code: String, message: String) : Exception(message)

class BindingStore(context: Context) {
    private val preferences = context.getSharedPreferences("material_bindings", Context.MODE_PRIVATE)
    val deviceId: String
        get() {
            val existing = preferences.getString("device_id", null)
            if (!existing.isNullOrBlank()) return existing
            return UUID.randomUUID().toString().also {
                preferences.edit().putString("device_id", it).apply()
            }
        }

    fun load(): List<ComputerBinding> {
        val raw = preferences.getString("bindings", "[]") ?: "[]"
        return runCatching {
            val array = JSONArray(raw)
            buildList {
                for (index in 0 until array.length()) {
                    val item = array.getJSONObject(index)
                    add(
                        ComputerBinding(
                            desktopId = item.getString("desktop_id"),
                            desktopName = item.optString("desktop_name", "电脑"),
                            accountId = item.getString("account_id"),
                            accountName = item.optString("account_name", "账号"),
                            host = item.getString("host"),
                            port = item.getInt("port"),
                            discoveryPort = item.optInt("discovery_port", 48761),
                            token = item.getString("token"),
                            deviceId = item.optString("device_id", deviceId),
                        )
                    )
                }
            }
        }.getOrDefault(emptyList())
    }

    fun upsert(binding: ComputerBinding) {
        val bindings = load().filterNot { it.key == binding.key } + binding
        val array = JSONArray()
        bindings.forEach {
            array.put(
                JSONObject()
                    .put("desktop_id", it.desktopId)
                    .put("desktop_name", it.desktopName)
                    .put("account_id", it.accountId)
                    .put("account_name", it.accountName)
                    .put("host", it.host)
                    .put("port", it.port)
                    .put("discovery_port", it.discoveryPort)
                    .put("token", it.token)
                    .put("device_id", it.deviceId)
            )
        }
        preferences.edit().putString("bindings", array.toString()).apply()
    }

    fun remove(key: String) {
        val array = JSONArray()
        load().filterNot { it.key == key }.forEach {
            array.put(
                JSONObject()
                    .put("desktop_id", it.desktopId)
                    .put("desktop_name", it.desktopName)
                    .put("account_id", it.accountId)
                    .put("account_name", it.accountName)
                    .put("host", it.host)
                    .put("port", it.port)
                    .put("discovery_port", it.discoveryPort)
                    .put("token", it.token)
                    .put("device_id", it.deviceId)
            )
        }
        preferences.edit().putString("bindings", array.toString()).apply()
    }

    fun loadPending(): List<PendingUpload> {
        val raw = preferences.getString("pending_uploads", "[]") ?: "[]"
        return runCatching {
            val array = JSONArray(raw)
            buildList {
                for (index in 0 until array.length()) {
                    val item = array.getJSONObject(index)
                    val spec = MaterialSpec(
                        id = item.getString("spec_id"),
                        name = item.getString("spec_name"),
                        codes = emptyList(),
                        hasMaterial = item.optBoolean("has_material", false),
                    )
                    val category = MaterialCategory(
                        id = item.getString("category_id"),
                        label = item.getString("category_label"),
                        color = item.optString("category_color", "#DDEBF7"),
                        specs = listOf(spec),
                        needsMaterial = !spec.hasMaterial,
                    )
                    add(
                        PendingUpload(
                            id = item.getString("id"),
                            uri = Uri.parse(item.getString("uri")),
                            bindingKey = item.getString("binding_key"),
                            category = category,
                            spec = spec,
                            state = item.optString("state", "pending"),
                        )
                    )
                }
            }
        }.getOrDefault(emptyList())
    }

    fun savePending(items: List<PendingUpload>) {
        val array = JSONArray()
        items.forEach { item ->
            array.put(
                JSONObject()
                    .put("id", item.id)
                    .put("uri", item.uri.toString())
                    .put("binding_key", item.bindingKey)
                    .put("category_id", item.category.id)
                    .put("category_label", item.category.label)
                    .put("category_color", item.category.color)
                    .put("spec_id", item.spec.id)
                    .put("spec_name", item.spec.name)
                    .put("has_material", item.spec.hasMaterial)
                    .put("state", item.state)
            )
        }
        preferences.edit().putString("pending_uploads", array.toString()).apply()
    }
}

class MaterialApi(private val context: Context) {
    private val jsonType = "application/json; charset=utf-8".toMediaType()
    private val client = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.MINUTES)
        .build()

    suspend fun pair(uri: Uri, deviceId: String, deviceName: String): ComputerBinding = withContext(Dispatchers.IO) {
        if (uri.scheme != "shopmaterial" || uri.host != "pair") {
            throw ApiException("invalid_qr", "这不是素材库助手绑定二维码")
        }
        val host = uri.getQueryParameter("host") ?: throw ApiException("invalid_qr", "二维码缺少电脑地址")
        val port = uri.getQueryParameter("port")?.toIntOrNull() ?: throw ApiException("invalid_qr", "二维码端口无效")
        val desktopId = uri.getQueryParameter("desktop_id") ?: throw ApiException("invalid_qr", "二维码缺少电脑标识")
        val accountId = uri.getQueryParameter("account_id") ?: throw ApiException("invalid_qr", "二维码缺少账号标识")
        val pairCode = uri.getQueryParameter("pair_code") ?: throw ApiException("invalid_qr", "二维码配对码无效")
        val hosts = buildList {
            add(host)
            uri.getQueryParameter("hosts")?.split(',')?.forEach { candidate ->
                if (candidate.isNotBlank()) add(candidate.trim())
            }
        }.distinct()
        val payload = JSONObject()
            .put("pair_code", pairCode)
            .put("device_id", deviceId)
            .put("device_name", deviceName)
        var connectedHost = host
        var result: JSONObject? = null
        var lastError: Exception? = null
        for (candidate in hosts) {
            try {
                result = executeJson(
                    Request.Builder()
                        .url("http://$candidate:$port/api/v1/pair")
                        .post(payload.toString().toRequestBody(jsonType))
                        .build()
                )
                connectedHost = candidate
                break
            } catch (error: Exception) {
                lastError = error
            }
        }
        val paired = result ?: throw (lastError ?: ApiException("offline", "无法连接电脑"))
        ComputerBinding(
            desktopId = paired.optString("desktop_id", desktopId),
            desktopName = paired.optString("desktop_name", "电脑"),
            accountId = paired.optString("account_id", accountId),
            accountName = paired.optString("account_name", "账号"),
            host = connectedHost,
            port = paired.optInt("http_port", port),
            discoveryPort = paired.optInt("discovery_port", 48761),
            token = paired.getString("access_token"),
            deviceId = deviceId,
        )
    }

    suspend fun ensureConnected(binding: ComputerBinding): ComputerBinding = withContext(Dispatchers.IO) {
        try {
            session(binding)
            return@withContext binding
        } catch (error: ApiException) {
            if (error.code == "account_inactive" || error.code == "unauthorized") throw error
        } catch (_: Exception) {
        }
        val discovered = discover(binding)
        session(discovered)
        discovered
    }

    suspend fun catalog(binding: ComputerBinding): Pair<ComputerBinding, List<MaterialCategory>> = withContext(Dispatchers.IO) {
        val connected = ensureConnected(binding)
        val result = executeJson(authenticatedRequest(connected, "/api/v1/catalog").get().build())
        val categories = buildList {
            val array = result.optJSONArray("categories") ?: JSONArray()
            for (index in 0 until array.length()) {
                val category = array.getJSONObject(index)
                val specs = buildList {
                    val specArray = category.optJSONArray("specs") ?: JSONArray()
                    for (specIndex in 0 until specArray.length()) {
                        val spec = specArray.getJSONObject(specIndex)
                        val codes = buildList {
                            val codeArray = spec.optJSONArray("codes") ?: JSONArray()
                            for (codeIndex in 0 until codeArray.length()) add(codeArray.getString(codeIndex))
                        }
                        add(
                            MaterialSpec(
                                spec.getString("id"),
                                spec.getString("name"),
                                codes,
                                spec.optBoolean("has_material", false),
                            )
                        )
                    }
                }
                add(
                    MaterialCategory(
                        id = category.getString("id"),
                        label = category.getString("label"),
                        color = category.optString("color", "#DDEBF7"),
                        specs = specs,
                        needsMaterial = category.optBoolean("needs_material", specs.any { !it.hasMaterial }),
                    )
                )
            }
        }
        connected to categories
    }

    suspend fun upload(
        binding: ComputerBinding,
        category: MaterialCategory,
        spec: MaterialSpec,
        uri: Uri,
    ): Pair<ComputerBinding, String> = withContext(Dispatchers.IO) {
        val connected = ensureConnected(binding)
        val mime = context.contentResolver.getType(uri) ?: "application/octet-stream"
        val extension = extensionFor(uri, mime)
        val request = authenticatedRequest(connected, "/api/v1/materials/${category.id}/${spec.id}")
            .header("Content-Type", mime)
            .header("X-File-Extension", extension)
            .post(ContentUriRequestBody(context, uri, mime.toMediaType()))
            .build()
        val result = executeJson(request)
        connected to result.getString("filename")
    }

    suspend fun images(
        binding: ComputerBinding,
        category: MaterialCategory,
        spec: MaterialSpec,
    ): Pair<ComputerBinding, List<RemoteMaterialImage>> = withContext(Dispatchers.IO) {
        val connected = ensureConnected(binding)
        val result = executeJson(
            authenticatedRequest(connected, "/api/v1/materials/${category.id}/${spec.id}").get().build()
        )
        val images = buildList {
            val array = result.optJSONArray("images") ?: JSONArray()
            for (index in 0 until array.length()) {
                val image = array.getJSONObject(index)
                add(RemoteMaterialImage(image.getString("id"), image.getString("name"), image.optLong("size")))
            }
        }
        connected to images
    }

    fun imageUrl(
        binding: ComputerBinding,
        category: MaterialCategory,
        spec: MaterialSpec,
        image: RemoteMaterialImage,
        original: Boolean,
    ): String = "http://${binding.host}:${binding.port}/api/v1/materials/${category.id}/${spec.id}/${image.id}" +
        "?variant=${if (original) "original" else "thumbnail"}"

    private fun session(binding: ComputerBinding) {
        executeJson(authenticatedRequest(binding, "/api/v1/session").get().build())
    }

    private fun authenticatedRequest(binding: ComputerBinding, path: String): Request.Builder =
        Request.Builder()
            .url("http://${binding.host}:${binding.port}$path")
            .header("Authorization", "Bearer ${binding.token}")

    private fun executeJson(request: Request): JSONObject {
        client.newCall(request).execute().use { response ->
            val text = response.body.string()
            val result = runCatching { JSONObject(text) }.getOrElse {
                throw ApiException("network", "电脑返回了无法识别的数据")
            }
            if (!response.isSuccessful || !result.optBoolean("ok", false)) {
                throw ApiException(result.optString("code", "request_failed"), result.optString("message", "请求失败"))
            }
            return result
        }
    }

    private fun discover(binding: ComputerBinding): ComputerBinding {
        DatagramSocket().use { socket ->
            socket.broadcast = true
            socket.soTimeout = 1800
            val request = JSONObject()
                .put("protocol", "shop-material-v1")
                .put("desktop_id", binding.desktopId)
                .put("account_id", binding.accountId)
                .put("device_id", binding.deviceId)
                .toString()
                .toByteArray()
            socket.send(
                DatagramPacket(
                    request,
                    request.size,
                    InetAddress.getByName("255.255.255.255"),
                    binding.discoveryPort,
                )
            )
            val buffer = ByteArray(4096)
            while (true) {
                val packet = DatagramPacket(buffer, buffer.size)
                socket.receive(packet)
                val result = JSONObject(String(packet.data, 0, packet.length))
                if (result.optString("desktop_id") != binding.desktopId) continue
                if (result.optString("account_id") != binding.accountId) continue
                if (result.optString("status") != "active") {
                    throw ApiException("account_inactive", "电脑当前打开的是另一个账号")
                }
                return binding.copy(
                    host = packet.address.hostAddress ?: binding.host,
                    port = result.getInt("port"),
                    desktopName = result.optString("desktop_name", binding.desktopName),
                )
            }
        }
    }

    private fun extensionFor(uri: Uri, mime: String): String {
        val byMime = mapOf(
            "image/jpeg" to ".jpg",
            "image/png" to ".png",
            "image/webp" to ".webp",
            "image/bmp" to ".bmp",
            "image/gif" to ".gif",
        )[mime.lowercase()]
        if (byMime != null) return byMime
        var name = ""
        context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
            if (it.moveToFirst()) name = it.getString(0) ?: ""
        }
        val extension = name.substringAfterLast('.', "").lowercase()
        if (extension in setOf("jpg", "jpeg", "png", "webp", "bmp", "gif")) return ".$extension"
        throw ApiException("unsupported", "该图片格式暂不支持，请选择 JPG、PNG 或 WEBP")
    }
}

private class ContentUriRequestBody(
    private val context: Context,
    private val uri: Uri,
    private val mediaType: MediaType,
) : RequestBody() {
    override fun contentType(): MediaType = mediaType

    override fun contentLength(): Long {
        context.contentResolver.query(uri, arrayOf(OpenableColumns.SIZE), null, null, null)?.use {
            if (it.moveToFirst()) return it.getLong(0)
        }
        return -1
    }

    override fun writeTo(sink: BufferedSink) {
        val input = context.contentResolver.openInputStream(uri)
            ?: throw ApiException("read_failed", "无法读取选中的图片")
        input.source().use { sink.writeAll(it) }
    }
}

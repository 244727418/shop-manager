package com.shopmanager.materialuploader

import android.app.Application
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.content.FileProvider
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.google.zxing.client.android.Intents
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import coil.compose.AsyncImage
import coil.request.ImageRequest
import kotlinx.coroutines.launch
import java.io.File
import java.util.UUID

class MainActivity : ComponentActivity() {
    private val viewModel by viewModels<MaterialViewModel>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                MaterialUploaderApp(viewModel)
            }
        }
        intent?.data?.let(viewModel::pair)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.data?.let(viewModel::pair)
    }
}

data class PendingUpload(
    val id: String = UUID.randomUUID().toString(),
    val uri: Uri,
    val bindingKey: String,
    val category: MaterialCategory,
    val spec: MaterialSpec,
    val state: String = "pending",
)

class MaterialViewModel(application: Application) : AndroidViewModel(application) {
    private val store = BindingStore(application)
    private val api = MaterialApi(application)
    val bindings = mutableStateListOf<ComputerBinding>().apply { addAll(store.load()) }
    val bindingStates = mutableStateMapOf<String, String>()
    val categories = mutableStateListOf<MaterialCategory>()
    val pendingImages = mutableStateListOf<PendingUpload>().apply { addAll(store.loadPending()) }
    val remoteImages = mutableStateListOf<RemoteMaterialImage>()
    var selectedBinding by mutableStateOf<ComputerBinding?>(null)
    var selectedCategory by mutableStateOf<MaterialCategory?>(null)
    var selectedSpec by mutableStateOf<MaterialSpec?>(null)
    var busy by mutableStateOf(false)
    var status by mutableStateOf("")
    var uploadedCount by mutableIntStateOf(0)
    var uploadTotal by mutableIntStateOf(0)
    var imagesLoading by mutableStateOf(false)
    var showPendingOnly by mutableStateOf(false)

    init {
        refreshBindingStates()
    }

    fun pair(uri: Uri) {
        viewModelScope.launch {
            busy = true
            status = "正在绑定电脑…"
            try {
                val deviceName = "${Build.MANUFACTURER} ${Build.MODEL}".trim()
                val binding = api.pair(uri, store.deviceId, deviceName)
                updateBinding(binding)
                bindingStates[binding.key] = "在线"
                status = "已绑定：${binding.desktopName} / ${binding.accountName}"
            } catch (error: Exception) {
                status = error.message ?: "绑定失败"
            } finally {
                busy = false
            }
        }
    }

    fun open(binding: ComputerBinding) {
        selectedBinding = binding
        selectedCategory = null
        selectedSpec = null
        remoteImages.clear()
        refresh()
    }

    fun refresh() {
        val binding = selectedBinding ?: return
        val categoryId = selectedCategory?.id
        val specId = selectedSpec?.id
        viewModelScope.launch {
            busy = true
            status = "正在连接 ${binding.desktopName}…"
            try {
                val (connected, result) = api.catalog(binding)
                updateBinding(connected)
                selectedBinding = connected
                categories.clear()
                categories.addAll(result)
                selectedCategory = result.firstOrNull { it.id == categoryId }
                selectedSpec = selectedCategory?.specs?.firstOrNull { it.id == specId }
                bindingStates[connected.key] = "在线"
                status = "已连接 ${connected.desktopName} / ${connected.accountName}"
                if (selectedSpec != null) refreshImages()
            } catch (error: Exception) {
                bindingStates[binding.key] = connectionLabel(error)
                status = error.message ?: "电脑离线或不在同一局域网"
            } finally {
                busy = false
            }
        }
    }

    fun remove(binding: ComputerBinding) {
        store.remove(binding.key)
        bindings.removeAll { it.key == binding.key }
        bindingStates.remove(binding.key)
        if (selectedBinding?.key == binding.key) closeBinding()
    }

    fun closeBinding() {
        selectedBinding = null
        selectedCategory = null
        selectedSpec = null
        categories.clear()
        remoteImages.clear()
        status = ""
    }

    fun selectCategory(category: MaterialCategory?) {
        selectedCategory = category
        selectedSpec = null
        remoteImages.clear()
    }

    fun togglePendingFilter() {
        showPendingOnly = !showPendingOnly
    }

    fun selectSpec(spec: MaterialSpec) {
        selectedSpec = spec
        remoteImages.clear()
        status = "已选择：${spec.name}"
        refreshImages()
    }

    fun setImages(uris: List<Uri>) {
        addImages(uris)
    }

    fun addImage(uri: Uri) {
        addImages(listOf(uri))
    }

    private fun addImages(uris: List<Uri>) {
        val binding = selectedBinding ?: return
        val category = selectedCategory ?: return
        val spec = selectedSpec ?: return
        uris.forEach { uri ->
            runCatching {
                getApplication<Application>().contentResolver.takePersistableUriPermission(
                    uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION,
                )
            }
            if (pendingImages.none {
                    it.uri == uri && it.bindingKey == binding.key &&
                        it.category.id == category.id && it.spec.id == spec.id
                }) {
                pendingImages += PendingUpload(
                    uri = uri,
                    bindingKey = binding.key,
                    category = category,
                    spec = spec,
                )
            }
        }
        store.savePending(pendingImages)
        status = "当前规格已选择 ${pendingForCurrent().size} 张图片"
    }

    fun pendingForCurrent(): List<PendingUpload> {
        val binding = selectedBinding ?: return emptyList()
        val category = selectedCategory ?: return emptyList()
        val spec = selectedSpec ?: return emptyList()
        return pendingImages.filter {
            it.bindingKey == binding.key && it.category.id == category.id && it.spec.id == spec.id
        }
    }

    fun removePending(id: String) {
        pendingImages.removeAll { it.id == id }
        store.savePending(pendingImages)
    }

    fun upload() {
        val initialBinding = selectedBinding ?: return
        val category = selectedCategory ?: return
        val spec = selectedSpec ?: return
        val queue = pendingForCurrent().filter { it.state != "uploaded" }
        if (queue.isEmpty()) {
            status = "请先选择图片或拍照"
            return
        }
        viewModelScope.launch {
            busy = true
            uploadedCount = 0
            uploadTotal = queue.size
            var binding = initialBinding
            queue.forEachIndexed { index, pending ->
                status = "正在上传 ${index + 1}/${queue.size}"
                try {
                    val (connected, _) = api.upload(binding, category, spec, pending.uri)
                    binding = connected
                    uploadedCount += 1
                    updatePendingState(pending.id, "uploaded")
                } catch (_: Exception) {
                    updatePendingState(pending.id, "failed")
                }
            }
            updateBinding(binding)
            selectedBinding = binding
            val failedCount = queue.count { item -> pendingImages.firstOrNull { it.id == item.id }?.state == "failed" }
            status = if (failedCount == 0) {
                "上传完成，共 $uploadedCount 张"
            } else {
                "已上传 $uploadedCount 张，失败 $failedCount 张；点击上传可重试"
            }
            busy = false
            refreshImages()
        }
    }

    fun refreshImages() {
        val binding = selectedBinding ?: return
        val category = selectedCategory ?: return
        val spec = selectedSpec ?: return
        viewModelScope.launch {
            imagesLoading = true
            try {
                val (connected, images) = api.images(binding, category, spec)
                if (
                    selectedBinding?.key == binding.key && selectedCategory?.id == category.id &&
                    selectedSpec?.id == spec.id
                ) {
                    updateBinding(connected)
                    selectedBinding = connected
                    remoteImages.clear()
                    remoteImages.addAll(images)
                }
            } catch (error: Exception) {
                if (selectedCategory?.id == category.id && selectedSpec?.id == spec.id) {
                    status = error.message ?: "读取电脑素材失败"
                }
            } finally {
                if (selectedCategory?.id == category.id && selectedSpec?.id == spec.id) {
                    imagesLoading = false
                }
            }
        }
    }

    fun imageUrl(image: RemoteMaterialImage, original: Boolean): String? {
        val binding = selectedBinding ?: return null
        val category = selectedCategory ?: return null
        val spec = selectedSpec ?: return null
        return api.imageUrl(binding, category, spec, image, original)
    }

    private fun updatePendingState(id: String, state: String) {
        val index = pendingImages.indexOfFirst { it.id == id }
        if (index >= 0) {
            pendingImages[index] = pendingImages[index].copy(state = state)
            store.savePending(pendingImages)
        }
    }

    private fun updateBinding(binding: ComputerBinding) {
        val index = bindings.indexOfFirst { it.key == binding.key }
        if (index >= 0) bindings[index] = binding else bindings.add(binding)
        store.upsert(binding)
    }

    private fun refreshBindingStates() {
        bindings.forEach { binding ->
            bindingStates[binding.key] = "检测中"
            viewModelScope.launch {
                try {
                    val connected = api.ensureConnected(binding)
                    updateBinding(connected)
                    bindingStates[binding.key] = "在线"
                } catch (error: Exception) {
                    bindingStates[binding.key] = connectionLabel(error)
                }
            }
        }
    }

    private fun connectionLabel(error: Exception): String =
        if (error is ApiException && error.code == "account_inactive") "账号未激活" else "离线"
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MaterialUploaderApp(viewModel: MaterialViewModel) {
    val scanner = rememberLauncherForActivityResult(ScanContract()) { result ->
        result.contents?.let { runCatching { Uri.parse(it) }.getOrNull() }?.let(viewModel::pair)
    }
    val scan = {
        scanner.launch(
            ScanOptions()
                .setPrompt("扫描电脑素材库中的绑定二维码")
                .setBeepEnabled(false)
                .setOrientationLocked(false)
                .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                .addExtra(Intents.Scan.SCAN_TYPE, Intents.Scan.MIXED_SCAN)
        )
    }
    val binding = viewModel.selectedBinding
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("素材库助手", fontWeight = FontWeight.Bold)
                        if (binding != null) {
                            Text(
                                "${binding.desktopName} / ${binding.accountName} · ${binding.shortCode}",
                                style = MaterialTheme.typography.labelSmall,
                            )
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color(0xFFF7F9FA)),
                navigationIcon = {
                    if (binding != null) {
                        TextButton(onClick = viewModel::closeBinding) { Text("返回") }
                    }
                },
                actions = {
                    if (binding == null) {
                        TextButton(onClick = scan) { Text("扫码绑定") }
                    } else {
                        TextButton(onClick = viewModel::refresh) { Text("刷新") }
                    }
                },
            )
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            if (binding == null) {
                BindingList(viewModel, scan)
            } else {
                CatalogScreen(viewModel)
            }
            if (viewModel.busy) {
                Surface(
                    modifier = Modifier.align(Alignment.Center),
                    tonalElevation = 6.dp,
                    shape = MaterialTheme.shapes.small,
                ) {
                    Row(
                        modifier = Modifier.padding(20.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        CircularProgressIndicator(modifier = Modifier.width(28.dp))
                        Spacer(Modifier.width(14.dp))
                        Text(viewModel.status.ifBlank { "处理中…" })
                    }
                }
            }
        }
    }
}

@Composable
private fun BindingList(viewModel: MaterialViewModel, scan: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(12.dp)) {
        if (viewModel.bindings.isEmpty()) {
            Column(
                modifier = Modifier.fillMaxWidth().padding(top = 80.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text("还没有绑定电脑", style = MaterialTheme.typography.titleMedium)
                Spacer(Modifier.height(8.dp))
                Text("打开电脑素材库，点击“手机绑定”后扫码。", color = Color.Gray)
                Spacer(Modifier.height(18.dp))
                Button(onClick = scan) { Text("扫码绑定电脑") }
            }
        } else {
            Text("已绑定的电脑账号", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(viewModel.bindings, key = { it.key }) { binding ->
                    Card(
                        modifier = Modifier.fillMaxWidth().clickable { viewModel.open(binding) },
                        colors = CardDefaults.cardColors(containerColor = Color.White),
                        border = BorderStroke(1.dp, Color(0xFFD7DEE3)),
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(14.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(binding.accountName, fontWeight = FontWeight.Bold)
                                Text("${binding.desktopName} · ${binding.host}", color = Color.Gray)
                                Text("标识 ${binding.shortCode}", style = MaterialTheme.typography.labelSmall)
                            }
                            Text(
                                viewModel.bindingStates[binding.key] ?: "未检测",
                                color = when (viewModel.bindingStates[binding.key]) {
                                    "在线" -> Color(0xFF218739)
                                    "账号未激活" -> Color(0xFFB26A00)
                                    else -> Color.Gray
                                },
                            )
                            TextButton(onClick = { viewModel.remove(binding) }) { Text("删除") }
                        }
                    }
                }
            }
        }
        if (viewModel.status.isNotBlank()) {
            Spacer(Modifier.height(12.dp))
            Text(viewModel.status, color = Color(0xFF176B87))
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun CatalogScreen(viewModel: MaterialViewModel) {
    val category = viewModel.selectedCategory
    BackHandler {
        if (category != null) viewModel.selectCategory(null) else viewModel.closeBinding()
    }
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(10.dp),
    ) {
        if (category == null) {
            val pendingCount = viewModel.categories.count { it.needsMaterial }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("选择商品类型", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                Bubble(
                    text = "待上传素材 $pendingCount",
                    color = if (viewModel.showPendingOnly) Color(0xFFFFD8A8) else Color(0xFFF2F3F4),
                ) { viewModel.togglePendingFilter() }
            }
            Spacer(Modifier.height(8.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(7.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                viewModel.categories.filter { !viewModel.showPendingOnly || it.needsMaterial }.forEach { item ->
                    Bubble(item.label, parseColor(item.color)) { viewModel.selectCategory(item) }
                }
            }
        } else {
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedButton(onClick = { viewModel.selectCategory(null) }) { Text("返回类型") }
                Spacer(Modifier.width(10.dp))
                Text(category.label, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.height(8.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(7.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                category.specs.filter { !viewModel.showPendingOnly || !it.hasMaterial }.forEach { spec ->
                    Bubble(
                        text = spec.name,
                        color = if (viewModel.selectedSpec?.id == spec.id) Color(0xFFBFE3D0) else Color(0xFFE8F1F7),
                    ) { viewModel.selectSpec(spec) }
                }
            }
            if (viewModel.selectedSpec != null) {
                Spacer(Modifier.height(14.dp))
                HorizontalDivider()
                ExistingMaterialPanel(viewModel)
                HorizontalDivider()
                UploadPanel(viewModel)
            }
        }
        if (viewModel.status.isNotBlank()) {
            Spacer(Modifier.height(14.dp))
            Text(viewModel.status, color = Color(0xFF176B87))
        }
    }
}

@Composable
private fun Bubble(text: String, color: Color, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.clickable(onClick = onClick),
        color = color,
        shape = MaterialTheme.shapes.extraLarge,
        border = BorderStroke(1.dp, Color(0xFFB8C5CC)),
    ) {
        Text(text, modifier = Modifier.padding(horizontal = 13.dp, vertical = 9.dp))
    }
}

@Composable
private fun UploadPanel(viewModel: MaterialViewModel) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val pending = viewModel.pendingForCurrent()
    val waiting = pending.count { it.state != "uploaded" }
    val photoPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.PickMultipleVisualMedia(50)
    ) { viewModel.setImages(it) }
    var cameraUri by remember { mutableStateOf<Uri?>(null) }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { success ->
        if (success) cameraUri?.let(viewModel::addImage)
    }
    Column(Modifier.fillMaxWidth().padding(top = 12.dp)) {
        Text("上传到：${viewModel.selectedSpec?.name}", fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = {
                    photoPicker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                },
            ) { Text("选择相册") }
            OutlinedButton(
                onClick = {
                    cameraUri = createCameraUri(context)
                    cameraUri?.let(camera::launch)
                },
            ) { Text("拍照") }
        }
        Spacer(Modifier.height(8.dp))
        Text(
            if (pending.isEmpty()) "尚未选择图片"
            else "已选择 ${pending.size} 张，待上传 $waiting 张",
            color = Color.Gray,
        )
        if (pending.isNotEmpty()) {
            Spacer(Modifier.height(7.dp))
            LazyRow(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                items(pending, key = { it.id }) { item ->
                    Box(Modifier.width(96.dp)) {
                        Column {
                            AsyncImage(
                                model = item.uri,
                                contentDescription = null,
                                contentScale = ContentScale.Crop,
                                modifier = Modifier.fillMaxWidth().aspectRatio(1f)
                                    .clip(RoundedCornerShape(4.dp))
                                    .background(Color(0xFFF0F2F3)),
                            )
                            Text(
                                when (item.state) {
                                    "uploaded" -> "已上传"
                                    "failed" -> "上传失败"
                                    else -> "待上传"
                                },
                                color = when (item.state) {
                                    "uploaded" -> Color(0xFF218739)
                                    "failed" -> Color(0xFFB42318)
                                    else -> Color.Gray
                                },
                                style = MaterialTheme.typography.labelSmall,
                            )
                        }
                        Surface(
                            modifier = Modifier.align(Alignment.TopEnd).clickable {
                                viewModel.removePending(item.id)
                            },
                            color = Color(0xCC202020),
                            shape = RoundedCornerShape(bottomStart = 6.dp),
                        ) {
                            Text("×", color = Color.White, modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp))
                        }
                    }
                }
            }
        }
        Spacer(Modifier.height(8.dp))
        Button(
            onClick = viewModel::upload,
            enabled = waiting > 0 && !viewModel.busy,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                if (viewModel.uploadTotal > 0 && viewModel.busy)
                    "上传中 ${viewModel.uploadedCount}/${viewModel.uploadTotal}"
                else if (pending.isNotEmpty() && waiting == 0) "已全部上传" else "开始上传原图"
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ExistingMaterialPanel(viewModel: MaterialViewModel) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val binding = viewModel.selectedBinding ?: return
    var preview by remember { mutableStateOf<RemoteMaterialImage?>(null) }
    Column(Modifier.fillMaxWidth().padding(vertical = 12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("电脑端素材", fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            TextButton(onClick = viewModel::refreshImages) { Text("刷新") }
        }
        when {
            viewModel.imagesLoading -> Text("正在读取缩略图…", color = Color.Gray)
            viewModel.remoteImages.isEmpty() -> Text("当前规格暂无素材", color = Color.Gray)
            else -> FlowRow(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                maxItemsInEachRow = 3,
            ) {
                viewModel.remoteImages.forEach { image ->
                    val url = viewModel.imageUrl(image, original = false)
                    Column(
                        modifier = Modifier.width(106.dp).clickable { preview = image },
                    ) {
                        AsyncImage(
                            model = authenticatedImageRequest(context, url, binding.token),
                            contentDescription = image.name,
                            contentScale = ContentScale.Crop,
                            modifier = Modifier.fillMaxWidth().aspectRatio(1f)
                                .clip(RoundedCornerShape(4.dp))
                                .background(Color(0xFFF0F2F3)),
                        )
                        Text(
                            image.name,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                            style = MaterialTheme.typography.labelSmall,
                        )
                    }
                }
            }
        }
    }
    preview?.let { image ->
        Dialog(
            onDismissRequest = { preview = null },
            properties = DialogProperties(usePlatformDefaultWidth = false),
        ) {
            Box(Modifier.fillMaxSize().background(Color.Black)) {
                AsyncImage(
                    model = authenticatedImageRequest(
                        context,
                        viewModel.imageUrl(image, original = true),
                        binding.token,
                    ),
                    contentDescription = image.name,
                    contentScale = ContentScale.Fit,
                    modifier = Modifier.fillMaxSize(),
                )
                Surface(
                    modifier = Modifier.align(Alignment.TopEnd).padding(14.dp).clickable { preview = null },
                    color = Color(0xAA202020),
                    shape = RoundedCornerShape(20.dp),
                ) {
                    Text("×", color = Color.White, modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp))
                }
            }
        }
    }
}

private fun authenticatedImageRequest(context: Context, url: String?, token: String): ImageRequest =
    ImageRequest.Builder(context)
        .data(url)
        .setHeader("Authorization", "Bearer $token")
        .crossfade(true)
        .build()

private fun createCameraUri(context: Context): Uri? = runCatching {
    val folder = File(context.cacheDir, "camera").apply { mkdirs() }
    val file = File.createTempFile("material_", ".jpg", folder)
    FileProvider.getUriForFile(context, "${context.packageName}.files", file)
}.getOrNull()

private fun parseColor(value: String): Color = runCatching {
    Color(android.graphics.Color.parseColor(value))
}.getOrDefault(Color(0xFFDDEBF7))

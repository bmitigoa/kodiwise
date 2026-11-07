package com.kodiwise.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import android.opengl.Matrix
import android.os.Bundle
import android.util.Log
import android.view.MotionEvent
import android.widget.Button
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import coil.load
import com.google.ar.core.Anchor
import com.google.ar.core.ArCoreApk
import com.google.ar.core.Config
import com.google.ar.core.Frame
import com.google.ar.core.Plane
import com.google.ar.core.Session
import com.google.ar.core.TrackingState
import com.google.firebase.firestore.DocumentSnapshot
import com.google.firebase.firestore.FirebaseFirestore
import java.util.concurrent.ConcurrentLinkedQueue
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10
import kotlin.math.atan2
import kotlin.math.max
import kotlin.math.sqrt

class ARViewActivity : AppCompatActivity(), GLSurfaceView.Renderer {

    private val db by lazy { FirebaseFirestore.getInstance() }

    private lateinit var glSurfaceView: GLSurfaceView
    private lateinit var tvHint: TextView
    private lateinit var cardAnchor: FrameLayout
    private lateinit var ivArPhoto: ImageView
    private lateinit var tvArTitle: TextView
    private lateinit var tvArLocation: TextView
    private lateinit var tvArMeta: TextView
    private lateinit var btnPrev: Button
    private lateinit var btnNext: Button
    private lateinit var btnResetAnchor: Button
    private lateinit var btnFullscreen: Button
    private lateinit var thumbnailStrip: LinearLayout

    private val backgroundRenderer = ARBackgroundRenderer()

    private var session: Session? = null
    private var installRequested = false
    private var surfaceWidth = 1
    private var surfaceHeight = 1

    private val tapQueue = ConcurrentLinkedQueue<Pair<Float, Float>>()
    private var anchor: Anchor? = null

    private var propertyId: String = ""
    private var pTitle: String = "Property"
    private var pLocation: String = "-"
    private var pMeta: String = ""
    private var pCoverUrl: String = ""

    private val imageUrls = mutableListOf<String>()
    private var currentImageIndex = 0

    private lateinit var scaleGestureDetector: android.view.ScaleGestureDetector
    private lateinit var rotationGestureDetector: RotationGestureDetector

    private var imageScale = 1f
    private var imageRotation = 0f

    companion object {
        private const val TAG = "RAW_AR"
        private const val RC_CAMERA = 1001
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        propertyId = intent.getStringExtra("PROPERTY_ID") ?: ""
        if (propertyId.isBlank()) {
            Toast.makeText(this, "Property missing", Toast.LENGTH_LONG).show()
            finish()
            return
        }

        setContentView(R.layout.activity_ar_view)
        ScreenHeader.bind(this, getString(R.string.title_ar_gallery))

        glSurfaceView = findViewById(R.id.glSurfaceView)
        tvHint = findViewById(R.id.tvArHint)
        cardAnchor = findViewById(R.id.cardAnchor)
        ivArPhoto = findViewById(R.id.ivArPhoto)
        tvArTitle = findViewById(R.id.tvArTitle)
        tvArLocation = findViewById(R.id.tvArLocation)
        tvArMeta = findViewById(R.id.tvArMeta)
        btnPrev = findViewById(R.id.btnPrev)
        btnNext = findViewById(R.id.btnNext)
        btnResetAnchor = findViewById(R.id.btnResetAnchor)
        btnFullscreen = findViewById(R.id.btnFullscreen)
        thumbnailStrip = findViewById(R.id.thumbnailStrip)

        setupLargePanelSize()
        setupGlView()
        setupGestures()
        setupButtons()
        setupFullscreenButton()

        loadPropertyForAr()
    }

    override fun onResume() {
        super.onResume()

        if (!hasCameraPermission()) {
            requestCameraPermission()
            return
        }

        try {
            tryCreateSession()
            session?.resume()
            glSurfaceView.onResume()
        } catch (t: Throwable) {
            Log.e(TAG, "onResume failed", t)
            Toast.makeText(this, "AR resume failed: ${t.message}", Toast.LENGTH_LONG).show()
            finish()
        }
    }

    override fun onPause() {
        super.onPause()
        glSurfaceView.onPause()
        session?.pause()
    }

    override fun onDestroy() {
        super.onDestroy()
        anchor?.detach()
        anchor = null
    }

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        GLES20.glClearColor(0f, 0f, 0f, 1f)
        backgroundRenderer.createOnGlThread()
        session?.setCameraTextureName(backgroundRenderer.textureId)
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        surfaceWidth = width
        surfaceHeight = height
        GLES20.glViewport(0, 0, width, height)
    }

    override fun onDrawFrame(gl: GL10?) {
        GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT or GLES20.GL_DEPTH_BUFFER_BIT)

        val currentSession = session ?: return

        try {
            currentSession.setCameraTextureName(backgroundRenderer.textureId)
            currentSession.setDisplayGeometry(getDisplayRotationCompat(), surfaceWidth, surfaceHeight)

            val frame = currentSession.update()
            val camera = frame.camera

            backgroundRenderer.draw(frame)

            if (camera.trackingState == TrackingState.TRACKING) {
                handleTap(frame)
                updateOverlayPosition(camera)
            } else {
                hideOverlay()
            }
        } catch (t: Throwable) {
            Log.e(TAG, "Render failed", t)
            runOnUiThread {
                Toast.makeText(this, "AR render failed: ${t.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun setupGlView() {
        glSurfaceView.setEGLContextClientVersion(2)
        glSurfaceView.setRenderer(this)
        glSurfaceView.renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
        glSurfaceView.preserveEGLContextOnPause = true

        glSurfaceView.setOnTouchListener { v, event ->
            if (event.action == MotionEvent.ACTION_UP) {
                tapQueue.offer(event.x to event.y)
                v.performClick()
            }
            true
        }
    }

    private fun setupLargePanelSize() {
        cardAnchor.post {
            val screenW = resources.displayMetrics.widthPixels
            val screenH = resources.displayMetrics.heightPixels

            val params = cardAnchor.layoutParams
            params.width = (screenW * 0.88f).toInt()
            params.height = (screenH * 0.42f).toInt()
            cardAnchor.layoutParams = params
        }
    }

    private fun setupButtons() {
        btnPrev.setOnClickListener {
            if (imageUrls.isEmpty()) return@setOnClickListener
            currentImageIndex = if (currentImageIndex == 0) imageUrls.lastIndex else currentImageIndex - 1
            showImageAt(currentImageIndex)
        }

        btnNext.setOnClickListener {
            if (imageUrls.isEmpty()) return@setOnClickListener
            currentImageIndex = if (currentImageIndex == imageUrls.lastIndex) 0 else currentImageIndex + 1
            showImageAt(currentImageIndex)
        }

        btnResetAnchor.setOnClickListener {
            anchor?.detach()
            anchor = null
            hideOverlay()
            Toast.makeText(this, "Tap a new surface to place the gallery again", Toast.LENGTH_SHORT).show()
        }
    }

    private fun setupFullscreenButton() {
        btnFullscreen.setOnClickListener {
            if (imageUrls.isEmpty()) return@setOnClickListener

            val intent = Intent(this, ARFullscreenImageActivity::class.java).apply {
                putStringArrayListExtra("IMAGE_URLS", ArrayList(imageUrls))
                putExtra("CURRENT_INDEX", currentImageIndex)
            }
            startActivity(intent)
        }
    }

    private fun setupGestures() {
        ivArPhoto.scaleType = ImageView.ScaleType.CENTER_CROP

        scaleGestureDetector = android.view.ScaleGestureDetector(
            this,
            object : android.view.ScaleGestureDetector.SimpleOnScaleGestureListener() {
                override fun onScale(detector: android.view.ScaleGestureDetector): Boolean {
                    imageScale *= detector.scaleFactor
                    imageScale = imageScale.coerceIn(1f, 4f)
                    applyImageTransform()
                    return true
                }
            }
        )

        rotationGestureDetector = RotationGestureDetector { deltaAngle ->
            imageRotation += deltaAngle
            applyImageTransform()
        }

        ivArPhoto.setOnTouchListener { _, event ->
            scaleGestureDetector.onTouchEvent(event)
            rotationGestureDetector.onTouchEvent(event)
            event.pointerCount >= 2
        }
    }

    private fun resetImageTransform() {
        imageScale = 1f
        imageRotation = 0f
        applyImageTransform()
    }

    private fun applyImageTransform() {
        ivArPhoto.pivotX = ivArPhoto.width / 2f
        ivArPhoto.pivotY = ivArPhoto.height / 2f
        ivArPhoto.scaleX = imageScale
        ivArPhoto.scaleY = imageScale
        ivArPhoto.rotation = imageRotation
    }

    private fun hasCameraPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED
    }

    private fun requestCameraPermission() {
        ActivityCompat.requestPermissions(
            this,
            arrayOf(Manifest.permission.CAMERA),
            RC_CAMERA
        )
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)

        if (requestCode == RC_CAMERA) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                onResume()
            } else {
                // No camera, no AR: show the listing details instead of closing.
                ArLauncher.openFallback(this, propertyId, ArLauncher.REASON_CAMERA_DENIED)
                finish()
            }
        }
    }

    private fun tryCreateSession() {
        if (session != null) return

        val availability = ArCoreApk.getInstance().checkAvailability(this)
        Log.d(TAG, "AR availability = $availability")

        if (availability.isTransient) {
            Toast.makeText(this, "Checking AR support...", Toast.LENGTH_SHORT).show()
            return
        }

        if (!availability.isSupported) {
            Toast.makeText(this, "AR is not supported on this device", Toast.LENGTH_LONG).show()
            finish()
            return
        }

        when (ArCoreApk.getInstance().requestInstall(this, !installRequested)) {
            ArCoreApk.InstallStatus.INSTALL_REQUESTED -> {
                installRequested = true
                Toast.makeText(this, "Complete AR setup, then reopen AR", Toast.LENGTH_LONG).show()
                return
            }

            ArCoreApk.InstallStatus.INSTALLED -> {
                session = Session(this)

                val config = Config(session).apply {
                    planeFindingMode = Config.PlaneFindingMode.HORIZONTAL_AND_VERTICAL
                    focusMode = Config.FocusMode.AUTO
                    updateMode = Config.UpdateMode.LATEST_CAMERA_IMAGE
                    lightEstimationMode = Config.LightEstimationMode.DISABLED
                }

                session?.configure(config)
                Log.d(TAG, "Raw ARCore session created")
            }
        }
    }

    private fun loadPropertyForAr() {
        db.collection("properties").document(propertyId).get()
            .addOnSuccessListener { doc ->
                pTitle = doc.getString("title") ?: "Untitled"
                pLocation = doc.getString("locationName")
                    ?: doc.getString("location")
                            ?: "-"

                val bedrooms = (doc.getLong("bedrooms") ?: 0L).toInt()
                val bathrooms = (doc.getLong("bathrooms") ?: 0L).toInt()

                val quoted = (
                        doc.getLong("quotedRent")?.toInt()
                            ?: doc.getDouble("quotedRent")?.toInt()
                            ?: doc.getString("quotedRent")?.toIntOrNull()
                            ?: 0
                        )

                pMeta = "$bedrooms beds • $bathrooms baths • KES $quoted"
                pCoverUrl = doc.getString("coverImageUrl") ?: ""

                imageUrls.clear()
                imageUrls.addAll(extractImageUrls(doc))

                if (imageUrls.isEmpty() && pCoverUrl.isNotBlank()) {
                    imageUrls.add(pCoverUrl)
                }

                currentImageIndex = 0
                tvArTitle.text = pTitle
                tvArLocation.text = pLocation
                tvArMeta.text = pMeta

                if (imageUrls.isNotEmpty()) {
                    showImageAt(0)
                    renderThumbnails()
                }

                tvHint.text = "Move phone slowly, then tap a floor or flat surface to place the property gallery"
            }
            .addOnFailureListener { e ->
                Toast.makeText(this, "AR load failed: ${e.message}", Toast.LENGTH_LONG).show()
                finish()
            }
    }

    private fun extractImageUrls(doc: DocumentSnapshot): List<String> {
        val result = mutableListOf<String>()

        val possibleFields = listOf(
            "imageUrls",
            "galleryImageUrls",
            "galleryUrls",
            "images",
            "photos",
            "propertyImages"
        )

        if (pCoverUrl.isNotBlank()) {
            result.add(pCoverUrl)
        }

        for (field in possibleFields) {
            val value = doc.get(field)
            if (value is List<*>) {
                value.forEach { item ->
                    val url = item?.toString()?.trim().orEmpty()
                    if (url.isNotBlank()) {
                        result.add(url)
                    }
                }
            }
        }

        return result.distinct()
    }

    private fun showImageAt(index: Int) {
        if (imageUrls.isEmpty()) return

        currentImageIndex = index.coerceIn(0, imageUrls.lastIndex)

        ivArPhoto.load(imageUrls[currentImageIndex]) {
            crossfade(true)
        }

        resetImageTransform()
        updateThumbnailSelection()
    }

    private fun renderThumbnails() {
        thumbnailStrip.removeAllViews()

        imageUrls.forEachIndexed { index, url ->
            val thumb = ImageView(this).apply {
                val size = dp(80)
                layoutParams = LinearLayout.LayoutParams(size, size).apply {
                    marginEnd = dp(8)
                }
                scaleType = ImageView.ScaleType.CENTER_CROP
                setBackgroundColor(0xFFFFFFFF.toInt())
                alpha = if (index == currentImageIndex) 1f else 0.55f
                load(url)
                setOnClickListener {
                    showImageAt(index)
                }
            }

            thumbnailStrip.addView(thumb)
        }
    }

    private fun updateThumbnailSelection() {
        for (i in 0 until thumbnailStrip.childCount) {
            val child = thumbnailStrip.getChildAt(i)
            child.alpha = if (i == currentImageIndex) 1f else 0.55f
        }
    }

    private fun handleTap(frame: Frame) {
        val tap = tapQueue.poll() ?: return

        val camera = frame.camera
        if (camera.trackingState != TrackingState.TRACKING) return

        for (hit in frame.hitTest(tap.first, tap.second)) {
            val trackable = hit.trackable
            val isPlaneHit = trackable is Plane && trackable.isPoseInPolygon(hit.hitPose)

            if (isPlaneHit) {
                anchor?.detach()
                anchor = hit.createAnchor()

                runOnUiThread {
                    cardAnchor.visibility = FrameLayout.VISIBLE
                    Toast.makeText(this, "Gallery placed in AR", Toast.LENGTH_SHORT).show()
                }
                return
            }
        }

        runOnUiThread {
            Toast.makeText(this, "No flat surface detected. Move phone and tap again.", Toast.LENGTH_SHORT).show()
        }
    }

    private fun updateOverlayPosition(camera: com.google.ar.core.Camera) {
        val currentAnchor = anchor
        if (currentAnchor == null || currentAnchor.trackingState != TrackingState.TRACKING) {
            hideOverlay()
            return
        }

        val proj = FloatArray(16)
        val view = FloatArray(16)
        val model = FloatArray(16)
        val mv = FloatArray(16)
        val mvp = FloatArray(16)

        camera.getProjectionMatrix(proj, 0, 0.1f, 100f)
        camera.getViewMatrix(view, 0)
        currentAnchor.pose.toMatrix(model, 0)

        Matrix.multiplyMM(mv, 0, view, 0, model, 0)
        Matrix.multiplyMM(mvp, 0, proj, 0, mv, 0)

        val worldPoint = floatArrayOf(0f, 0f, 0f, 1f)
        val clip = FloatArray(4)
        Matrix.multiplyMV(clip, 0, mvp, 0, worldPoint, 0)

        if (clip[3] <= 0f) {
            hideOverlay()
            return
        }

        val ndcX = clip[0] / clip[3]
        val ndcY = clip[1] / clip[3]
        val ndcZ = clip[2] / clip[3]

        if (ndcX < -1f || ndcX > 1f || ndcY < -1f || ndcY > 1f || ndcZ < -1f || ndcZ > 1f) {
            hideOverlay()
            return
        }

        val screenX = (ndcX * 0.5f + 0.5f) * surfaceWidth
        val screenY = (-ndcY * 0.5f + 0.5f) * surfaceHeight

        val distance = calculateDistanceFromCamera(currentAnchor)
        val baseScale = (1.7f / distance).coerceIn(0.86f, 1.28f)

        cardAnchor.post {
            cardAnchor.visibility = FrameLayout.VISIBLE

            val cardW = max(cardAnchor.width, 1)
            val cardH = max(cardAnchor.height, 1)

            val rawX = screenX - cardW / 2f
            val rawY = screenY - cardH / 2f

            val minX = dp(8).toFloat()
            val minY = dp(150).toFloat()
            val maxX = surfaceWidth - cardW - dp(8).toFloat()
            val maxY = surfaceHeight - cardH - dp(170).toFloat()

            cardAnchor.x = rawX.coerceIn(minX, maxX)
            cardAnchor.y = rawY.coerceIn(minY, maxY)

            cardAnchor.scaleX = baseScale
            cardAnchor.scaleY = baseScale
        }
    }

    private fun calculateDistanceFromCamera(anchor: Anchor): Float {
        val tx = anchor.pose.tx()
        val ty = anchor.pose.ty()
        val tz = anchor.pose.tz()
        return sqrt(tx * tx + ty * ty + tz * tz)
    }

    private fun hideOverlay() {
        cardAnchor.post {
            cardAnchor.visibility = FrameLayout.GONE
        }
    }

    @Suppress("DEPRECATION")
    private fun getDisplayRotationCompat(): Int {
        return windowManager.defaultDisplay.rotation
    }

    private fun dp(value: Int): Int {
        return (value * resources.displayMetrics.density).toInt()
    }

    private class RotationGestureDetector(
        private val onRotation: (Float) -> Unit
    ) {
        private var previousAngle = 0f
        private var rotating = false

        fun onTouchEvent(event: MotionEvent): Boolean {
            if (event.pointerCount < 2) {
                rotating = false
                return false
            }

            val angle = calculateAngle(event)

            when (event.actionMasked) {
                MotionEvent.ACTION_POINTER_DOWN -> {
                    previousAngle = angle
                    rotating = true
                }

                MotionEvent.ACTION_MOVE -> {
                    if (rotating) {
                        val delta = angle - previousAngle
                        previousAngle = angle
                        onRotation(delta)
                    }
                }

                MotionEvent.ACTION_POINTER_UP,
                MotionEvent.ACTION_UP,
                MotionEvent.ACTION_CANCEL -> {
                    rotating = false
                }
            }
            return true
        }

        private fun calculateAngle(event: MotionEvent): Float {
            val dx = event.getX(1) - event.getX(0)
            val dy = event.getY(1) - event.getY(0)
            return Math.toDegrees(atan2(dy.toDouble(), dx.toDouble())).toFloat()
        }
    }
}
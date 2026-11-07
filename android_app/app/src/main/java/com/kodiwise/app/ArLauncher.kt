package com.kodiwise.app

import android.app.Activity
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.google.ar.core.ArCoreApk

/**
 * Opens a listing in AR when this phone supports ARCore, otherwise in
 * ARFallbackActivity (listing details without the camera).
 */
object ArLauncher {

    const val EXTRA_PROPERTY_ID = "PROPERTY_ID"
    const val EXTRA_FALLBACK_REASON = "com.kodiwise.app.AR_FALLBACK_REASON"
    const val REASON_UNSUPPORTED = "unsupported"
    const val REASON_CAMERA_DENIED = "camera_denied"

    private const val TAG = "ArLauncher"
    private const val RECHECK_MS = 200L
    private const val MAX_CHECKS = 10 // ~2 s while ARCore is still deciding

    /** Supported, or installable with Google Play Services for AR -> AR view. */
    fun isArCapable(availability: ArCoreApk.Availability): Boolean = availability.isSupported

    fun open(activity: Activity, propertyId: String, attempt: Int = 0) {
        val availability = ArCoreApk.getInstance().checkAvailability(activity)
        Log.d(TAG, "AR availability = $availability (check ${attempt + 1})")

        if (availability.isTransient && attempt < MAX_CHECKS) {
            Handler(Looper.getMainLooper()).postDelayed({
                if (!activity.isFinishing && !activity.isDestroyed) open(activity, propertyId, attempt + 1)
            }, RECHECK_MS)
            return
        }

        if (isArCapable(availability)) {
            activity.startActivity(
                Intent(activity, ARViewActivity::class.java).putExtra(EXTRA_PROPERTY_ID, propertyId)
            )
        } else {
            // UNSUPPORTED_DEVICE_NOT_CAPABLE, or still unknown after ~2 s:
            // show the listing without AR rather than a screen that closes.
            openFallback(activity, propertyId, REASON_UNSUPPORTED)
        }
    }

    fun openFallback(activity: Activity, propertyId: String, reason: String) {
        activity.startActivity(
            Intent(activity, ARFallbackActivity::class.java)
                .putExtra(EXTRA_PROPERTY_ID, propertyId)
                .putExtra(EXTRA_FALLBACK_REASON, reason)
        )
    }
}

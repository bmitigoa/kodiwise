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

    /** ARCore says this device can't do AR. */
    const val REASON_UNSUPPORTED = "unsupported"
    /** ARCore couldn't tell (error, or still checking after ~2 s). Retryable. */
    const val REASON_UNKNOWN = "unknown"
    const val REASON_CAMERA_DENIED = "camera_denied"

    private const val TAG = "ArLauncher"
    private const val RECHECK_MS = 200L
    private const val MAX_CHECKS = 10 // ~2 s while ARCore is still deciding

    /**
     * Fallback reason for a final (non-transient or timed-out) availability,
     * or null when AR can be opened (supported, or installable with Google
     * Play Services for AR).
     */
    fun fallbackReason(availability: ArCoreApk.Availability): String? = when {
        availability.isSupported -> null
        availability == ArCoreApk.Availability.UNSUPPORTED_DEVICE_NOT_CAPABLE -> REASON_UNSUPPORTED
        else -> REASON_UNKNOWN
    }

    /**
     * Runs the ARCore availability check, re-checking while the result is
     * transient (up to ~2 s), then reports the fallback reason (null = AR OK).
     */
    fun check(activity: Activity, onResult: (String?) -> Unit, attempt: Int = 0) {
        val availability = ArCoreApk.getInstance().checkAvailability(activity)
        Log.d(TAG, "AR availability = $availability (check ${attempt + 1})")
        if (availability.isTransient && attempt < MAX_CHECKS) {
            Handler(Looper.getMainLooper()).postDelayed({
                if (!activity.isFinishing && !activity.isDestroyed) check(activity, onResult, attempt + 1)
            }, RECHECK_MS)
            return
        }
        onResult(fallbackReason(availability))
    }

    /** "View in AR": AR view if ARCore can run it, otherwise the fallback. */
    fun open(activity: Activity, propertyId: String) {
        check(activity, { reason ->
            if (reason == null) openAr(activity, propertyId)
            else openFallback(activity, propertyId, reason)
        })
    }

    fun openAr(activity: Activity, propertyId: String) {
        activity.startActivity(
            Intent(activity, ARViewActivity::class.java).putExtra(EXTRA_PROPERTY_ID, propertyId)
        )
    }

    fun openFallback(activity: Activity, propertyId: String, reason: String) {
        activity.startActivity(
            Intent(activity, ARFallbackActivity::class.java)
                .putExtra(EXTRA_PROPERTY_ID, propertyId)
                .putExtra(EXTRA_FALLBACK_REASON, reason)
        )
    }
}

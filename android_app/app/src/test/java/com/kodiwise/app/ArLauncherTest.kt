package com.kodiwise.app

import com.google.ar.core.ArCoreApk.Availability
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ArLauncherTest {

    @Test
    fun supportedOrInstallableOpensAr() {
        assertNull(ArLauncher.fallbackReason(Availability.SUPPORTED_INSTALLED))
        assertNull(ArLauncher.fallbackReason(Availability.SUPPORTED_NOT_INSTALLED))
        assertNull(ArLauncher.fallbackReason(Availability.SUPPORTED_APK_TOO_OLD))
    }

    @Test
    fun notCapableIsUnsupported() {
        assertEquals(ArLauncher.REASON_UNSUPPORTED, ArLauncher.fallbackReason(Availability.UNSUPPORTED_DEVICE_NOT_CAPABLE))
    }

    @Test
    fun unknownResultsAreRetryable() {
        assertEquals(ArLauncher.REASON_UNKNOWN, ArLauncher.fallbackReason(Availability.UNKNOWN_ERROR))
        assertEquals(ArLauncher.REASON_UNKNOWN, ArLauncher.fallbackReason(Availability.UNKNOWN_TIMED_OUT))
        // Still checking after the ~2 s budget
        assertEquals(ArLauncher.REASON_UNKNOWN, ArLauncher.fallbackReason(Availability.UNKNOWN_CHECKING))
    }
}

package com.kodiwise.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PhotoRulesTest {

    @Test fun landscapeIsScaledToLongSide1600() {
        assertEquals(1600 to 1200, PhotoRules.scaledSize(4000, 3000))
    }

    @Test fun portraitIsScaledToLongSide1600() {
        assertEquals(900 to 1600, PhotoRules.scaledSize(2250, 4000))
    }

    @Test fun smallPhotoIsNeverUpscaled() {
        assertEquals(800 to 600, PhotoRules.scaledSize(800, 600))
        assertEquals(1600 to 1000, PhotoRules.scaledSize(1600, 1000))
    }

    @Test fun extremeAspectKeepsAtLeastOnePixel() {
        val (w, h) = PhotoRules.scaledSize(10000, 2)
        assertEquals(1600, w)
        assertTrue(h >= 1)
    }

    @Test(expected = IllegalArgumentException::class)
    fun zeroSizeIsRejected() {
        PhotoRules.scaledSize(0, 100)
    }

    @Test fun sampleSizeKeepsLongSideAtOrAboveTarget() {
        assertEquals(1, PhotoRules.sampleSize(1600, 1200))
        assertEquals(1, PhotoRules.sampleSize(3000, 2000))
        assertEquals(2, PhotoRules.sampleSize(4000, 3000))
        assertEquals(4, PhotoRules.sampleSize(8000, 6000))
        for ((w, h) in listOf(4032 to 3024, 6000 to 4000, 12000 to 9000)) {
            val s = PhotoRules.sampleSize(w, h)
            assertTrue(maxOf(w, h) / s >= PhotoRules.MAX_LONG_SIDE)
        }
    }

    @Test fun photoPathMatchesStorageRules() {
        assertEquals("properties/abc/photos/u-1.jpg", PhotoRules.photoPath("abc", "u-1"))
        assertTrue(PhotoRules.photoPath("abc", "u-1").startsWith(PhotoRules.photosFolder("abc") + "/"))
    }

    @Test fun limitsMatchTheSpec() {
        assertEquals(8, PhotoRules.MAX_PHOTOS)
        assertEquals(1600, PhotoRules.MAX_LONG_SIDE)
        assertEquals(80, PhotoRules.QUALITY_STEPS.first())
        assertTrue(PhotoRules.TARGET_BYTES <= 400 * 1024)
        assertEquals(2 * 1024 * 1024, PhotoRules.MAX_FILE_BYTES)
    }

    @Test fun slotsLeftNeverGoesNegative() {
        assertEquals(8, PhotoRules.slotsLeft(0))
        assertEquals(3, PhotoRules.slotsLeft(5))
        assertEquals(0, PhotoRules.slotsLeft(8))
        assertEquals(0, PhotoRules.slotsLeft(12))
    }
}

package com.kodiwise.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class RentRangeTest {

    @Test
    fun aboveWithinBelow() {
        assertEquals(RangePosition.ABOVE, RentRange.position(90_000.0, 40_000.0, 80_000.0, "high"))
        assertEquals(RangePosition.WITHIN, RentRange.position(60_000.0, 40_000.0, 80_000.0, "high"))
        assertEquals(RangePosition.BELOW, RentRange.position(30_000.0, 40_000.0, 80_000.0, "low"))
    }

    @Test
    fun boundsCountAsWithin() {
        assertEquals(RangePosition.WITHIN, RentRange.position(40_000.0, 40_000.0, 80_000.0, "high"))
        assertEquals(RangePosition.WITHIN, RentRange.position(80_000.0, 40_000.0, 80_000.0, "high"))
    }

    @Test
    fun noBadgeWhenConfidenceIsNone() {
        assertNull(RentRange.position(90_000.0, 40_000.0, 80_000.0, "none"))
    }

    @Test
    fun noBadgeForListingsWithoutRange() {
        assertNull(RentRange.position(60_000.0, null, null, null))
        assertNull(RentRange.position(60_000.0, 40_000.0, null, "high"))
    }

    @Test
    fun missingConfidenceStillShowsBadge() {
        // Range saved by an API version without location_confidence.
        assertEquals(RangePosition.WITHIN, RentRange.position(60_000.0, 40_000.0, 80_000.0, null))
    }

    @Test
    fun invalidRangeShowsNoBadge() {
        assertNull(RentRange.position(60_000.0, 0.0, 80_000.0, "high"))
        assertNull(RentRange.position(60_000.0, 90_000.0, 80_000.0, "high"))
        assertNull(RentRange.position(0.0, 40_000.0, 80_000.0, "high"))
    }
}

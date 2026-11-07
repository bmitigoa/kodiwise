package com.kodiwise.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LocationConfidenceHintTest {

    @Test
    fun lowShowsRoughHint() {
        assertEquals(
            "Few listings in this area. Treat this estimate as rough.",
            PredictionResponse.locationConfidenceHint("low")
        )
    }

    @Test
    fun noneShowsNairobiAverageHint() {
        assertEquals(
            "Not enough local data. This estimate is based mostly on the Nairobi average.",
            PredictionResponse.locationConfidenceHint("none")
        )
    }

    @Test
    fun highShowsNoHint() {
        assertNull(PredictionResponse.locationConfidenceHint("high"))
    }

    @Test
    fun missingFieldShowsNoHint() {
        assertNull(PredictionResponse.locationConfidenceHint(null))
    }
}

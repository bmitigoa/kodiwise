package com.kodiwise.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class WhyEstimateTest {
    private fun f(label: String, kes: Double) =
        ExplanationFactor(name = label, label = label, direction = if (kes >= 0) "+" else "-", effectKes = kes)

    @Test fun formatsRoundedSignedKes() {
        assertEquals("+KES 15,000", WhyEstimate.formatEffect(14_870.0))
        assertEquals("-KES 4,500", WhyEstimate.formatEffect(-4_612.0))
        assertEquals("+KES 60,500", WhyEstimate.formatEffect(60_467.0))
    }

    @Test fun visibleSortsByMagnitudeCapsAtFiveAndDropsTiny() {
        val list = listOf(f("a", 100.0), f("b", -9000.0), f("c", 3000.0), f("d", 20000.0),
            f("e", 1500.0), f("f", -800.0), f("g", 6000.0))
        val v = WhyEstimate.visible(list).map { it.label }
        assertEquals(listOf("d", "b", "g", "c", "e"), v)
    }

    @Test fun barFractionsAreRelativeToTheLargest() {
        val fr = WhyEstimate.barFractions(listOf(f("a", 20000.0), f("b", -10000.0), f("c", 100.0)))
        assertEquals(1f, fr[0], 1e-6f)
        assertEquals(0.5f, fr[1], 1e-6f)
        assertTrue(fr[2] >= 0.08f)
        assertTrue(WhyEstimate.barFractions(emptyList()).isEmpty())
    }

    @Test fun describeIsPlainLanguage() {
        assertEquals("Kilimani location, raises the estimate by about KES 15,000",
            WhyEstimate.describe(f("Kilimani location", 15000.0)))
        assertEquals("Not furnished, lowers the estimate by about KES 5,500",
            WhyEstimate.describe(f("Not furnished", -5567.0)))
    }
}

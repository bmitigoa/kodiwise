package com.kodiwise.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LocationMatchTest {

    private val known = listOf("Kilimani", "South B", "Westlands")

    @Test
    fun exactAndCaseInsensitiveMatchReturnCanonicalName() {
        assertEquals("Kilimani", LocationDirectory.match("Kilimani", known))
        assertEquals("Kilimani", LocationDirectory.match("kilimani", known))
        assertEquals("South B", LocationDirectory.match("  SOUTH b ", known))
    }

    @Test
    fun partialOrUnknownTextIsRejected() {
        assertNull(LocationDirectory.match("Kilim", known))
        assertNull(LocationDirectory.match("Westland", known))
        assertNull(LocationDirectory.match("Nowhereville", known))
        assertNull(LocationDirectory.match("", known))
        assertNull(LocationDirectory.match("   ", known))
    }
}

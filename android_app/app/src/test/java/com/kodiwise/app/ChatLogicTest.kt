package com.kodiwise.app

import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ChatLogicTest {

    private fun user(t: String) = ChatMessage(ChatRole.USER, t)
    private fun bot(t: String, kind: ChatKind = ChatKind.NORMAL) = ChatMessage(ChatRole.BOT, t, kind = kind)

    @Test fun onlyTheLastSixRealTurnsAreSent() {
        val msgs = (1..10).flatMap { listOf(user("q$it"), bot("a$it")) }
        val body = ChatLogic.buildRequest(msgs)
        assertEquals(6, body.messages.size)
        assertEquals("user", body.messages.first().role)
        assertEquals("a10", body.messages.last().text)
    }

    @Test fun historyStartsOnAUserTurn() {
        val msgs = listOf(user("a"), bot("b"), user("c"), bot("d"), user("e"), bot("f"), user("g"))
        val body = ChatLogic.buildRequest(msgs)             // last 6 start with a bot turn: dropped
        assertEquals(listOf("user", "model", "user", "model", "user"), body.messages.map { it.role })
        assertEquals("c", body.messages.first().text)
    }

    @Test fun limitAndErrorBubblesNeverGoBackToTheServer() {
        val msgs = listOf(bot("Hi! welcome", ChatKind.LIMIT), user("q"), bot("limit text", ChatKind.LIMIT), user("q2"))
        val body = ChatLogic.buildRequest(msgs)
        assertEquals(listOf("q", "q2"), body.messages.map { it.text })
    }

    @Test fun longTextIsTrimmedToTheServerLimit() {
        val body = ChatLogic.buildRequest(listOf(user("x".repeat(900))))
        assertEquals(ChatLogic.MAX_CHARS, body.messages.single().text.length)
    }

    @Test fun canSendRejectsBlankAndTooLong() {
        assertFalse(ChatLogic.canSend(null))
        assertFalse(ChatLogic.canSend("   "))
        assertTrue(ChatLogic.canSend(" 2 bed in Kilimani "))
        assertFalse(ChatLogic.canSend("x".repeat(501)))
    }

    @Test fun limitStatusesMapToTheRightUiState() {
        assertFalse(ChatLogic.isLimit("ok"))
        assertTrue(ChatLogic.isLimit("busy"))
        assertTrue(ChatLogic.inputDisabled("limit_user"))
        assertTrue(ChatLogic.inputDisabled("limit_global"))
        assertFalse(ChatLogic.inputDisabled("busy"))          // temporary: typing stays on
        assertEquals(ChatKind.NORMAL, ChatLogic.kindFor("ok"))
        assertEquals(ChatKind.LIMIT, ChatLogic.kindFor("limit_user"))
    }

    @Test fun verdictsMatchTheFairRentSheet() {
        assertEquals(FairVerdict.ABOVE, ChatLogic.verdict("above_estimated_range"))
        assertEquals(FairVerdict.WITHIN, ChatLogic.verdict("within_estimated_range"))
        assertEquals(FairVerdict.BELOW, ChatLogic.verdict("below_estimated_range"))
        assertEquals(FairVerdict.NO_VERDICT, ChatLogic.verdict("no_verdict"))
        assertEquals(FairVerdict.NO_VERDICT, ChatLogic.verdict(null))
    }

    @Test fun serverReplyWithCardsParses() {
        val json = """
            {"status":"ok","reply":"About KES 60,000.","remaining_today":14,"show_assistant_button":false,
             "cards":[{"type":"estimate","area":"Kilimani","estimate_kes":60000,"range_low_kes":42000,
                       "range_high_kes":90000,"confidence":"high","bedrooms":2,"bathrooms":2},
                      {"type":"areas","title":"budget","budget":"KES 60,000","bedrooms":2,"bathrooms":2,
                       "comfortable":[{"area":"Kasarani","estimate_kes":40000,"range_low_kes":28000,
                                       "range_high_kes":60000,"confidence":"low","distance_km":null}],
                       "stretch":[],"thin":["Kasarani"]}]}
        """.trimIndent()
        val r = Gson().fromJson(json, ChatReply::class.java)
        assertEquals(14, r.remainingToday)
        assertEquals(2, r.cards.size)
        val row = ChatLogic.toAreaRow(r.cards[0])!!
        assertEquals("Kilimani", row.area)
        assertEquals(90000.0, row.rangeHighKes, 0.0)
        val comfortable = ChatLogic.toAreaRow(r.cards[1].comfortable.single())!!
        assertEquals("low", comfortable.locationConfidence)
        assertNull(comfortable.distanceKm)
    }

    @Test fun incompleteRowsAreSkippedNotDrawn() {
        assertNull(ChatLogic.toAreaRow(ChatAreaRow("Kilimani", 60000.0, null, 90000.0, "high")))
        assertNull(ChatLogic.toAreaRow(ChatAreaRow("Kilimani", 60000.0, 90000.0, 42000.0, "high")))   // low > high
        assertNull(ChatLogic.toAreaRow(ChatAreaRow(null, 60000.0, 42000.0, 90000.0, "high")))
    }

    @Test fun limitReplyParsesWithoutCards() {
        val r = Gson().fromJson("""{"status":"limit_user","reply":"x","show_assistant_button":true}""", ChatReply::class.java)
        assertTrue(r.showAssistantButton)
        assertTrue(r.cards.isEmpty())
    }

    @Test fun errorAndRemainingText() {
        assertTrue(ChatLogic.errorMessage(401).contains("sign in", ignoreCase = true))
        assertTrue(ChatLogic.errorMessage(null).contains("connection"))
        assertEquals("No messages left today", ChatLogic.remainingText(0))
        assertEquals("1 message left today", ChatLogic.remainingText(1))
        assertEquals("14 messages left today", ChatLogic.remainingText(14))
        assertNull(ChatLogic.remainingText(null))
    }
}

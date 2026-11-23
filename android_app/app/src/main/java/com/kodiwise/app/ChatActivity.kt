package com.kodiwise.app

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.button.MaterialButton
import com.google.android.material.chip.Chip
import com.google.android.material.chip.ChipGroup
import com.google.android.material.textfield.TextInputEditText
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.launch

/**
 * "Ask KodiWise": a short chat about Nairobi rents, answered by Gemini (free tier) using KodiWise's own
 * estimates as tools. Nothing is stored on the server except a daily message count; the app sends only
 * the last few messages. The numbers shown on cards come from the estimate tools, not from the model.
 */
class ChatActivity : AppCompatActivity() {

    private val messages = mutableListOf<ChatMessage>()
    private var sending = false
    private var inputLocked = false
    private var lastBody: ChatRequestBody? = null
    private var opening = false

    private lateinit var adapter: ChatAdapter
    private lateinit var list: RecyclerView
    private lateinit var input: TextInputEditText
    private lateinit var btnSend: MaterialButton
    private lateinit var groupError: View
    private lateinit var tvError: TextView
    private lateinit var tvRemaining: TextView
    private lateinit var suggestionsScroll: View

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!AuthManager.isLoggedIn()) {
            finish()
            return
        }
        setContentView(R.layout.activity_chat)
        ScreenHeader.bind(this, getString(R.string.title_chat))

        list = findViewById(R.id.chatList)
        input = findViewById(R.id.etChat)
        btnSend = findViewById(R.id.btnChatSend)
        groupError = findViewById(R.id.groupChatError)
        tvError = findViewById(R.id.tvChatError)
        tvRemaining = findViewById(R.id.tvRemaining)
        suggestionsScroll = findViewById(R.id.suggestionsScroll)

        adapter = ChatAdapter(::openEstimate, ::openAssistant)
        list.layoutManager = LinearLayoutManager(this).apply { stackFromEnd = true }
        list.adapter = adapter

        restore(savedInstanceState)
        if (messages.isEmpty()) messages += ChatMessage(ChatRole.BOT, getString(R.string.chat_welcome), kind = ChatKind.LIMIT)

        val chips = findViewById<ChipGroup>(R.id.suggestions)
        listOf(R.string.chat_suggest_1, R.string.chat_suggest_2, R.string.chat_suggest_3).forEach { res ->
            chips.addView(Chip(this).apply {
                setText(res)
                setOnClickListener { send(getString(res)) }
            })
        }

        btnSend.setOnClickListener { send(input.text?.toString()) }
        input.setOnEditorActionListener { _, action, _ ->
            if (action == EditorInfo.IME_ACTION_SEND) {
                send(input.text?.toString()); true
            } else false
        }
        findViewById<View>(R.id.btnChatRetry).setOnClickListener { lastBody?.let { request(it) } }

        render()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putString(KEY_MESSAGES, Gson().toJson(messages))
        outState.putBoolean(KEY_LOCKED, inputLocked)
    }

    private fun restore(state: Bundle?) {
        val json = state?.getString(KEY_MESSAGES) ?: return
        val type = object : TypeToken<List<ChatMessage>>() {}.type
        runCatching { Gson().fromJson<List<ChatMessage>>(json, type) }.getOrNull()?.let {
            messages.clear(); messages.addAll(it)
        }
        inputLocked = state.getBoolean(KEY_LOCKED, false)
    }

    private fun send(raw: String?) {
        if (sending || inputLocked || !ChatLogic.canSend(raw)) return
        messages += ChatMessage(ChatRole.USER, raw!!.trim())
        input.setText("")
        groupError.visibility = View.GONE
        request(ChatLogic.buildRequest(messages))
    }

    private fun request(body: ChatRequestBody) {
        lastBody = body
        sending = true
        groupError.visibility = View.GONE
        render()
        lifecycleScope.launch {
            try {
                val resp = ChatClient.send(body)
                val reply = resp.body()
                if (resp.isSuccessful && reply != null) {
                    onReply(reply)
                } else {
                    fail(ChatLogic.errorMessage(resp.code()))
                }
            } catch (e: Exception) {
                fail(ChatLogic.errorMessage(null))
            }
        }
    }

    private fun onReply(r: ChatReply) {
        sending = false
        val kind = ChatLogic.kindFor(r.status)
        messages += ChatMessage(ChatRole.BOT, r.reply, if (kind == ChatKind.NORMAL) r.cards else emptyList(), kind, r.showAssistantButton)
        if (ChatLogic.inputDisabled(r.status)) inputLocked = true
        val left = when (r.status) {
            ChatLogic.STATUS_OK -> r.remainingToday
            ChatLogic.STATUS_LIMIT_USER -> 0
            else -> null
        }
        ChatLogic.remainingText(left)?.let { tvRemaining.text = it; tvRemaining.visibility = View.VISIBLE }
        render()
    }

    private fun fail(message: String) {
        sending = false
        tvError.text = message
        groupError.visibility = View.VISIBLE
        render()
    }

    private fun render() {
        val started = messages.any { it.role == ChatRole.USER }
        suggestionsScroll.visibility = if (started || inputLocked) View.GONE else View.VISIBLE
        input.isEnabled = !inputLocked
        btnSend.isEnabled = !inputLocked && !sending
        adapter.submit(messages, sending)
        list.scrollToPosition(adapter.itemCount - 1)
    }

    private fun openEstimate(area: String, beds: Int, baths: Int) {
        if (opening) return
        opening = true
        lifecycleScope.launch {
            val error = EstimateLauncher.open(this@ChatActivity, area, beds, baths)
            opening = false
            if (error != null) Toast.makeText(this@ChatActivity, error, Toast.LENGTH_LONG).show()
        }
    }

    private fun openAssistant() {
        startActivity(Intent(this, FindAreasActivity::class.java))
    }

    companion object {
        private const val KEY_MESSAGES = "messages"
        private const val KEY_LOCKED = "locked"
    }
}

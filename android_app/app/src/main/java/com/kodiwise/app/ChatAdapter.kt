package com.kodiwise.app

import android.content.res.ColorStateList
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.RecyclerView

/** Bubbles for the chat, with tool-backed cards (estimate, area lists, listings) under a bot answer. */
class ChatAdapter(
    private val onOpenEstimate: (area: String, bedrooms: Int, bathrooms: Int) -> Unit,
    private val onOpenAssistant: () -> Unit
) : RecyclerView.Adapter<RecyclerView.ViewHolder>() {

    private var items: List<ChatMessage> = emptyList()
    private var typing = false

    fun submit(messages: List<ChatMessage>, showTyping: Boolean) {
        items = messages
        typing = showTyping
        notifyDataSetChanged()
    }

    override fun getItemCount() = items.size + if (typing) 1 else 0

    override fun getItemViewType(position: Int): Int = when {
        position >= items.size -> TYPE_TYPING
        items[position].role == ChatRole.USER -> TYPE_USER
        else -> TYPE_BOT
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
        val inf = LayoutInflater.from(parent.context)
        return when (viewType) {
            TYPE_USER -> UserHolder(inf.inflate(R.layout.item_chat_user, parent, false))
            TYPE_BOT -> BotHolder(inf.inflate(R.layout.item_chat_bot, parent, false))
            else -> object : RecyclerView.ViewHolder(inf.inflate(R.layout.item_chat_typing, parent, false)) {}
        }
    }

    override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
        when (holder) {
            is UserHolder -> holder.text.text = items[position].text
            is BotHolder -> bindBot(holder, items[position])
        }
    }

    private class UserHolder(v: View) : RecyclerView.ViewHolder(v) {
        val text: TextView = v.findViewById(R.id.tvUserText)
    }

    private class BotHolder(v: View) : RecyclerView.ViewHolder(v) {
        val text: TextView = v.findViewById(R.id.tvBotText)
        val cards: LinearLayout = v.findViewById(R.id.botCards)
        val assistant: View = v.findViewById(R.id.btnOpenAssistant)
    }

    private fun bindBot(h: BotHolder, m: ChatMessage) {
        h.text.text = m.text
        h.assistant.visibility = if (m.showAssistantButton) View.VISIBLE else View.GONE
        h.assistant.setOnClickListener { onOpenAssistant() }
        h.cards.removeAllViews()
        m.cards.forEach { addCard(h.cards, it) }
    }

    private fun addCard(into: LinearLayout, c: ChatCard) {
        val ctx = into.context
        when (c.type) {
            "estimate" -> {
                val row = ChatLogic.toAreaRow(c) ?: return
                val beds = c.bedrooms ?: 1
                val baths = c.bathrooms ?: 1
                val badge = if (c.verdict != null) verdictLabel(ctx, c) else null
                into.addView(AreaCardBinder.bind(into, row, badge) { onOpenEstimate(it.area, beds, baths) })
            }
            "areas" -> {
                val beds = c.bedrooms ?: 1
                val baths = c.bathrooms ?: 1
                if (c.title == "budget") {
                    c.budget?.let { section(into, ctx.getString(R.string.chat_card_budget, it)) }
                    group(into, ctx.getString(R.string.results_comfortable), c.comfortable, beds, baths)
                    group(into, ctx.getString(R.string.results_stretch), c.stretch, beds, baths)
                } else {
                    section(into, ctx.getString(R.string.chat_card_compare))
                    c.areas.forEach { addAreaRow(into, it, beds, baths) }
                }
            }
            "listings" -> {
                section(into, ctx.getString(R.string.chat_listings_title, c.total ?: c.listings.size))
                c.listings.forEach { into.addView(listingCard(into, it)) }
                section(into, ctx.getString(R.string.chat_listings_more))
            }
        }
    }

    private fun group(into: LinearLayout, title: String, rows: List<ChatAreaRow>, beds: Int, baths: Int) {
        if (rows.none { ChatLogic.toAreaRow(it) != null }) return
        section(into, title)
        rows.forEach { addAreaRow(into, it, beds, baths) }
    }

    private fun addAreaRow(into: LinearLayout, r: ChatAreaRow, beds: Int, baths: Int) {
        val row = ChatLogic.toAreaRow(r) ?: return
        into.addView(AreaCardBinder.bind(into, row) { onOpenEstimate(it.area, beds, baths) })
    }

    private fun section(into: LinearLayout, text: String) {
        val v = LayoutInflater.from(into.context).inflate(R.layout.item_chat_section, into, false) as TextView
        v.text = text
        into.addView(v)
    }

    private fun verdictLabel(ctx: android.content.Context, c: ChatCard): String {
        val asking = c.askingRentKes?.let { ListingCard.formatKes(it) }.orEmpty()
        val res = when (ChatLogic.verdict(c.verdict)) {
            FairVerdict.ABOVE -> R.string.chat_verdict_above
            FairVerdict.WITHIN -> R.string.chat_verdict_within
            FairVerdict.BELOW -> R.string.chat_verdict_below
            FairVerdict.NO_VERDICT -> R.string.chat_verdict_none
        }
        return ctx.getString(res, asking)
    }

    private fun listingCard(parent: ViewGroup, l: ChatListing): View {
        val ctx = parent.context
        val v = LayoutInflater.from(ctx).inflate(R.layout.item_chat_listing, parent, false)
        v.findViewById<TextView>(R.id.tvListTitle).text = l.title
        val beds = l.bedrooms?.let { ctx.resources.getQuantityString(R.plurals.beds, it, it) }
        val baths = l.bathrooms?.let { ctx.resources.getQuantityString(R.plurals.baths, it, it) }
        v.findViewById<TextView>(R.id.tvListMeta).text =
            listOfNotNull(l.area.ifBlank { null }, beds, baths).joinToString(" · ")
        v.findViewById<TextView>(R.id.tvListRent).text =
            ctx.getString(R.string.listing_price_month, ListingCard.formatKes(l.rentKes))
        val badge = when (l.badge) {
            "above_estimated_range" -> R.string.chat_badge_above
            "within_estimated_range" -> R.string.chat_badge_within
            "below_estimated_range" -> R.string.chat_badge_below
            else -> null
        }
        if (badge != null) {
            v.findViewById<TextView>(R.id.tvListBadge).apply {
                setText(badge)
                backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(context, R.color.kw_primary_container))
                setTextColor(ContextCompat.getColor(context, R.color.kw_on_primary_container))
                visibility = View.VISIBLE
            }
        }
        return v
    }

    companion object {
        private const val TYPE_USER = 0
        private const val TYPE_BOT = 1
        private const val TYPE_TYPING = 2
    }
}

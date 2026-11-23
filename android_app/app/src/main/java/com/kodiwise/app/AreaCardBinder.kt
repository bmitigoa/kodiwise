package com.kodiwise.app

import android.content.res.ColorStateList
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.core.widget.TextViewCompat

/** Draws one area/estimate card (item_area_card), shared by the Rent Assistant results and the chat. */
object AreaCardBinder {

    /**
     * @param badge optional label shown in the corner (a distance, or a fair-rent verdict)
     * @param onClick null makes the card non-interactive
     */
    fun bind(parent: ViewGroup, row: AreaRow, badge: String? = null, onClick: ((AreaRow) -> Unit)?): View {
        val ctx = parent.context
        val v = LayoutInflater.from(ctx).inflate(R.layout.item_area_card, parent, false)
        v.findViewById<TextView>(R.id.tvAreaName).text = row.area
        v.findViewById<TextView>(R.id.tvAreaEstimate).text =
            ctx.getString(R.string.listing_price_month, ListingCard.formatKes(row.estimateKes))
        v.findViewById<TextView>(R.id.tvAreaLow).text = ListingCard.formatKes(row.rangeLowKes)
        v.findViewById<TextView>(R.id.tvAreaHigh).text = ListingCard.formatKes(row.rangeHighKes)

        val badgeText = badge ?: row.distanceKm?.let { AreaAssistant.formatKm(it) }
        if (badgeText != null) {
            v.findViewById<TextView>(R.id.tvAreaDistance).apply {
                text = badgeText
                backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(context, R.color.kw_primary_container))
                setTextColor(ContextCompat.getColor(context, R.color.kw_on_primary_container))
                visibility = View.VISIBLE
            }
        }

        if (AreaAssistant.needsWarning(row.locationConfidence)) {
            val low = row.locationConfidence == "low"
            val chip = v.findViewById<TextView>(R.id.tvAreaConfidence)
            val fg = ColorStateList.valueOf(
                ContextCompat.getColor(ctx, if (low) R.color.kw_on_secondary_container else R.color.kw_on_neutral_chip)
            )
            chip.setText(if (low) R.string.area_rough else R.string.area_no_data)
            chip.backgroundTintList = ColorStateList.valueOf(
                ContextCompat.getColor(ctx, if (low) R.color.kw_secondary_container else R.color.kw_neutral_chip)
            )
            chip.setTextColor(fg)
            TextViewCompat.setCompoundDrawableTintList(chip, fg)
            chip.visibility = View.VISIBLE
        }

        val bar = v.findViewById<View>(R.id.areaRangeBar)
        val marker = v.findViewById<View>(R.id.areaRangeMarker)
        val fraction = AreaAssistant.rangeFraction(row.rangeLowKes, row.estimateKes, row.rangeHighKes)
        bar.post {
            val x = ((bar.width - marker.width) * fraction).toFloat()
            marker.translationX = if (bar.layoutDirection == View.LAYOUT_DIRECTION_RTL) -x else x
        }
        bar.contentDescription = ctx.getString(
            R.string.cd_area_range, ListingCard.formatKes(row.rangeLowKes), ListingCard.formatKes(row.rangeHighKes)
        )

        val hint = v.findViewById<TextView>(R.id.tvAreaTapHint)
        if (onClick != null) {
            v.setOnClickListener { onClick(row) }
        } else {
            v.isClickable = false
            v.isFocusable = false
            hint.visibility = View.GONE
        }
        return v
    }
}

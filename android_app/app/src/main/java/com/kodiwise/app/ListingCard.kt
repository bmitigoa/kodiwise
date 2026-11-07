package com.kodiwise.app

import android.content.Context
import android.content.res.ColorStateList
import android.view.View
import android.widget.ImageView
import android.widget.TextView
import androidx.annotation.ColorRes
import androidx.core.content.ContextCompat
import coil.load
import com.google.android.material.chip.Chip
import java.text.NumberFormat
import java.util.Locale
import kotlin.math.roundToInt

/**
 * Presentation helpers shared by every listing card and detail screen:
 * status/band badges, price text, beds/baths/size chips and the cover
 * placeholder. Display only -- callers still decide what data to show.
 */
object ListingCard {

    fun formatKes(value: Number): String {
        val nf = NumberFormat.getNumberInstance(Locale.US)
        nf.maximumFractionDigits = 0
        return "KES ${nf.format(value)}"
    }

    fun priceText(ctx: Context, price: Number): String =
        ctx.getString(R.string.listing_price_month, formatKes(price))

    private fun tint(tv: TextView, @ColorRes bg: Int, @ColorRes fg: Int) {
        val ctx = tv.context
        tv.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(ctx, bg))
        tv.setTextColor(ContextCompat.getColor(ctx, fg))
    }

    /** Approval status badge: pending gold, approved green, rejected red. */
    fun bindStatus(tv: TextView, statusRaw: String) {
        when (statusRaw.trim().lowercase()) {
            "approved" -> {
                tv.setText(R.string.status_approved)
                tint(tv, R.color.kw_primary_container, R.color.kw_on_primary_container)
            }
            "rejected" -> {
                tv.setText(R.string.status_rejected)
                tint(tv, R.color.kw_error_container, R.color.kw_on_error_container)
            }
            else -> {
                tv.setText(R.string.status_pending)
                tint(tv, R.color.kw_secondary_container, R.color.kw_on_secondary_container)
            }
        }
    }

    /** Quoted rent vs the model's estimate (stored rentBand LOW/FAIR/HIGH). */
    fun bindBand(tv: TextView, bandRaw: String) {
        when (bandRaw.ifBlank { "FAIR" }.uppercase()) {
            "HIGH" -> {
                tv.setText(R.string.band_high)
                tint(tv, R.color.kw_error_container, R.color.kw_on_error_container)
            }
            "LOW" -> {
                tv.setText(R.string.band_low)
                tint(tv, R.color.kw_tertiary_container, R.color.kw_on_tertiary_container)
            }
            else -> {
                tv.setText(R.string.band_fair)
                tint(tv, R.color.kw_primary_container, R.color.kw_on_primary_container)
            }
        }
    }

    fun bindChips(beds: Chip, baths: Chip, size: Chip?, bedrooms: Int, bathrooms: Int, sqM: Double?) {
        val res = beds.resources
        beds.text = res.getQuantityString(R.plurals.beds, bedrooms, bedrooms)
        baths.text = res.getQuantityString(R.plurals.baths, bathrooms, bathrooms)
        if (size != null) {
            if (sqM != null && sqM > 0) {
                size.text = res.getString(R.string.listing_size_sqm, sqM.roundToInt())
                size.visibility = View.VISIBLE
            } else {
                size.visibility = View.GONE
            }
        }
    }

    /** Loads the cover, or shows the branded placeholder when there is none. */
    fun bindCover(iv: ImageView, url: String) {
        if (url.isNotBlank()) {
            iv.scaleType = ImageView.ScaleType.CENTER_CROP
            iv.load(url) { crossfade(true) }
        } else {
            iv.scaleType = ImageView.ScaleType.CENTER
            iv.setImageResource(R.drawable.ic_home)
        }
    }
}

package com.kodiwise.app

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import com.google.android.material.chip.Chip
import androidx.recyclerview.widget.RecyclerView

class LandlordPropertyAdapter(
    private val items: MutableList<Property>,
    private val onClick: (Property) -> Unit,
    private val onDelete: (Property) -> Unit
) : RecyclerView.Adapter<LandlordPropertyAdapter.VH>() {

    class VH(v: View) : RecyclerView.ViewHolder(v) {

        val ivCover: ImageView = v.findViewById(R.id.ivCover)

        val tvTitle: TextView = v.findViewById(R.id.tvTitle)
        val tvLocation: TextView = v.findViewById(R.id.tvLocation)

        val tvStatus: TextView = v.findViewById(R.id.tvStatus)
        val tvBand: TextView = v.findViewById(R.id.tvBand)
        val tvPrice: TextView = v.findViewById(R.id.tvPrice)
        val chipBeds: Chip = v.findViewById(R.id.chipBeds)
        val chipBaths: Chip = v.findViewById(R.id.chipBaths)
        val chipSize: Chip = v.findViewById(R.id.chipSize)
        val notesBox: View = v.findViewById(R.id.notesBox)

        val tvAdminNotesLabel: TextView = v.findViewById(R.id.tvAdminNotesLabel)
        val tvAdminNotes: TextView = v.findViewById(R.id.tvAdminNotes)

        val btnDelete: View = v.findViewById(R.id.btnDelete)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_landlord_property, parent, false)
        return VH(view)
    }

    override fun onBindViewHolder(h: VH, position: Int) {

        val p = items[position]
        val ctx = h.itemView.context

        h.tvTitle.text = p.title.ifBlank { ctx.getString(R.string.listing_untitled) }
        h.tvLocation.text = p.location.ifBlank { "-" }
        ListingCard.bindStatus(h.tvStatus, p.status)
        ListingCard.bindBand(h.tvBand, p.rentBand)
        h.tvPrice.text = ListingCard.priceText(ctx, p.price)
        ListingCard.bindChips(h.chipBeds, h.chipBaths, h.chipSize, p.bedrooms, p.bathrooms, p.sqM)
        ListingCard.bindCover(h.ivCover, p.coverImageUrl)

        // ✅ SHOW ADMIN REVIEW COMMENT
        val notes = p.adminNotes.trim()

        h.notesBox.visibility = if (notes.isNotEmpty()) View.VISIBLE else View.GONE
        if (notes.isNotEmpty()) {

            h.tvAdminNotesLabel.visibility = View.VISIBLE
            h.tvAdminNotes.visibility = View.VISIBLE

            h.tvAdminNotes.text = notes

        } else {

            h.tvAdminNotesLabel.visibility = View.GONE
            h.tvAdminNotes.visibility = View.GONE
        }

        h.itemView.setOnClickListener { onClick(p) }
        h.btnDelete.setOnClickListener { onDelete(p) }
    }

    override fun getItemCount(): Int = items.size

    fun replaceAll(newItems: List<Property>) {
        items.clear()
        items.addAll(newItems)
        notifyDataSetChanged()
    }
}
package com.kodiwise.app

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.RecyclerView
import coil.load

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
        val tvMeta: TextView = v.findViewById(R.id.tvMeta)
        val tvBand: TextView = v.findViewById(R.id.tvBand)
        val tvPrice: TextView = v.findViewById(R.id.tvPrice)

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

        h.tvTitle.text = p.title.ifBlank { "Untitled" }
        h.tvLocation.text = p.location.ifBlank { "-" }

        val approval = p.prettyStatus().uppercase()
        h.tvStatus.text = approval

        val chipColor = when (approval.lowercase()) {
            "approved" -> android.R.color.holo_green_light
            "rejected" -> android.R.color.holo_red_light
            else -> android.R.color.darker_gray
        }

        h.tvStatus.setBackgroundColor(
            ContextCompat.getColor(ctx, chipColor)
        )

        h.tvMeta.text = "${p.bedrooms} Bedrooms • ${p.bathrooms} Bathrooms"

        val band = p.rentBand.ifBlank { "FAIR" }.uppercase()
        h.tvBand.text = band

        val bandColor = RentUtils.colorForBand(band)
        h.tvBand.setTextColor(ContextCompat.getColor(ctx, bandColor))

        h.tvPrice.text = "KES ${p.price}"

        if (p.coverImageUrl.isNotBlank()) {
            h.ivCover.load(p.coverImageUrl)
        } else {
            h.ivCover.setImageResource(android.R.color.darker_gray)
        }

        // ✅ SHOW ADMIN REVIEW COMMENT
        val notes = p.adminNotes.trim()

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
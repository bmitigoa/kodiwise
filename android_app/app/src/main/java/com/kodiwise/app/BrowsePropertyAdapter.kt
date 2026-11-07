package com.kodiwise.app

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import com.google.android.material.chip.Chip
import androidx.recyclerview.widget.RecyclerView

class BrowsePropertyAdapter(
    private val items: MutableList<Property>,
    private val onClick: (Property) -> Unit
) : RecyclerView.Adapter<BrowsePropertyAdapter.VH>() {

    private val allItems: MutableList<Property> = mutableListOf()

    class VH(v: View) : RecyclerView.ViewHolder(v) {
        val ivCover: ImageView = v.findViewById(R.id.ivCover)
        val tvTitle: TextView = v.findViewById(R.id.tvTitle)
        val tvLocation: TextView = v.findViewById(R.id.tvLocation)
        val tvPrice: TextView = v.findViewById(R.id.tvPrice)
        val tvStatus: TextView = v.findViewById(R.id.tvStatus)
        val tvBand: TextView = v.findViewById(R.id.tvBand)
        val chipBeds: Chip = v.findViewById(R.id.chipBeds)
        val chipBaths: Chip = v.findViewById(R.id.chipBaths)
        val chipSize: Chip = v.findViewById(R.id.chipSize)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_browse_property, parent, false)
        return VH(view)
    }

    override fun onBindViewHolder(h: VH, position: Int) {
        val p = items[position]

        val ctx = h.itemView.context
        h.tvTitle.text = p.title.ifBlank { ctx.getString(R.string.listing_untitled) }
        h.tvLocation.text = p.location.ifBlank { "-" }
        h.tvPrice.text = ListingCard.priceText(ctx, p.price)
        // Browse only lists approved listings, so the status badge is hidden.
        h.tvStatus.visibility = View.GONE
        ListingCard.bindBand(h.tvBand, p.rentBand)
        ListingCard.bindChips(h.chipBeds, h.chipBaths, h.chipSize, p.bedrooms, p.bathrooms, p.sqM)
        ListingCard.bindCover(h.ivCover, p.coverImageUrl)

        h.itemView.setOnClickListener { onClick(p) }
    }

    override fun getItemCount(): Int = items.size

    fun replaceAll(newItems: List<Property>) {
        allItems.clear()
        allItems.addAll(newItems)

        items.clear()
        items.addAll(newItems)

        notifyDataSetChanged()
    }

    fun filter(query: String) {
        val q = query.trim().lowercase()

        items.clear()

        if (q.isEmpty()) {
            items.addAll(allItems)
        } else {
            val filtered = allItems.filter { p ->
                val title = p.title.lowercase()
                val location = p.location.lowercase()
                val band = p.rentBand.lowercase()
                val price = p.price.toString().lowercase()
                val beds = p.bedrooms.toString().lowercase()
                val baths = p.bathrooms.toString().lowercase()

                title.contains(q) ||
                        location.contains(q) ||
                        band.contains(q) ||
                        price.contains(q) ||
                        beds.contains(q) ||
                        baths.contains(q)
            }
            items.addAll(filtered)
        }

        notifyDataSetChanged()
    }
}
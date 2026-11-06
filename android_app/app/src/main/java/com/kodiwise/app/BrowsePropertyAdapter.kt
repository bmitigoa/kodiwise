package com.kodiwise.app

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.RecyclerView
import coil.load

class BrowsePropertyAdapter(
    private val items: MutableList<Property>,
    private val onClick: (Property) -> Unit
) : RecyclerView.Adapter<BrowsePropertyAdapter.VH>() {

    private val allItems: MutableList<Property> = mutableListOf()

    class VH(v: View) : RecyclerView.ViewHolder(v) {
        val ivCover: ImageView = v.findViewById(R.id.ivCover)
        val tvTitle: TextView = v.findViewById(R.id.tvTitle)
        val tvLocation: TextView = v.findViewById(R.id.tvLocation)
        val tvMetaPrice: TextView = v.findViewById(R.id.tvMetaPrice)
        val tvBand: TextView = v.findViewById(R.id.tvBand)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_browse_property, parent, false)
        return VH(view)
    }

    override fun onBindViewHolder(h: VH, position: Int) {
        val p = items[position]

        h.tvTitle.text = p.title.ifBlank { "Untitled" }
        h.tvLocation.text = p.location.ifBlank { "-" }
        h.tvMetaPrice.text = "${p.bedrooms} bedrooms • ${p.bathrooms} bathrooms • KES ${p.price}"

        val band = p.rentBand.ifBlank { "FAIR" }.uppercase()
        h.tvBand.text = band
        h.tvBand.setTextColor(
            ContextCompat.getColor(h.itemView.context, RentUtils.colorForBand(band))
        )

        if (p.coverImageUrl.isNotBlank()) {
            h.ivCover.load(p.coverImageUrl) {
                crossfade(true)
            }
        } else {
            h.ivCover.setImageResource(android.R.color.darker_gray)
        }

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
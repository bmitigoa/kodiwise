package com.kodiwise.app

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.RecyclerView

class PropertyAdapter(
    private val items: MutableList<Property>,
    private val onClick: (Property) -> Unit
) : RecyclerView.Adapter<PropertyAdapter.PropertyVH>() {

    class PropertyVH(itemView: View) : RecyclerView.ViewHolder(itemView) {
        val tvTitle: TextView = itemView.findViewById(R.id.tvTitle)
        val tvLocation: TextView = itemView.findViewById(R.id.tvLocation)
        val tvBand: TextView = itemView.findViewById(R.id.tvBand)
        val tvMeta: TextView = itemView.findViewById(R.id.tvMeta)
        val tvPrice: TextView = itemView.findViewById(R.id.tvPrice)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): PropertyVH {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_property, parent, false)
        return PropertyVH(view)
    }

    override fun onBindViewHolder(holder: PropertyVH, position: Int) {
        val p = items[position]
        val ctx = holder.itemView.context

        holder.tvTitle.text = p.title.ifBlank { "Untitled" }
        holder.tvLocation.text = p.location.ifBlank { "-" }
        holder.tvMeta.text = "${p.bedrooms} bedrooms • ${p.bathrooms} bathrooms"

        val band = p.rentBand.ifBlank { "FAIR" }.uppercase()
        holder.tvBand.text = band

        val colorRes = RentUtils.colorForBand(band)
        val color = ContextCompat.getColor(ctx, colorRes)

        holder.tvBand.setTextColor(color)
        holder.tvPrice.setTextColor(color)
        holder.tvPrice.text = "KES ${p.price}"

        holder.itemView.setOnClickListener { onClick(p) }
    }

    override fun getItemCount(): Int = items.size

    fun replaceAll(newItems: List<Property>) {
        items.clear()
        items.addAll(newItems)
        notifyDataSetChanged()
    }
}
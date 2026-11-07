package com.kodiwise.app

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.widget.AppCompatButton
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.chip.Chip

class PendingApprovalAdapter(
    private val items: MutableList<Property>,
    private val onReview: (Property) -> Unit
) : RecyclerView.Adapter<PendingApprovalAdapter.VH>() {

    inner class VH(v: View) : RecyclerView.ViewHolder(v) {
        val ivCover: ImageView = v.findViewById(R.id.ivCover)
        val tvTitle: TextView = v.findViewById(R.id.tvTitle)
        val tvLocation: TextView = v.findViewById(R.id.tvLocation)
        val tvPrice: TextView = v.findViewById(R.id.tvPrice)
        val tvBand: TextView = v.findViewById(R.id.tvBand)
        val tvStatus: TextView = v.findViewById(R.id.tvStatus)
        val chipBeds: Chip = v.findViewById(R.id.chipBeds)
        val chipBaths: Chip = v.findViewById(R.id.chipBaths)
        val chipSize: Chip = v.findViewById(R.id.chipSize)
        val btnReview: AppCompatButton = v.findViewById(R.id.btnReview)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_pending_property, parent, false)
        return VH(view)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        val item = items[position]

        val ctx = holder.itemView.context
        holder.tvTitle.text = item.title.ifBlank { ctx.getString(R.string.listing_untitled) }
        holder.tvLocation.text = item.location.ifBlank { "-" }
        holder.tvPrice.text = ListingCard.priceText(ctx, item.price)
        ListingCard.bindStatus(holder.tvStatus, item.status)
        ListingCard.bindBand(holder.tvBand, item.rentBand)
        ListingCard.bindChips(holder.chipBeds, holder.chipBaths, holder.chipSize, item.bedrooms, item.bathrooms, item.sqM)

        val imageUrl = when {
            item.coverImageUrl.isNotBlank() -> item.coverImageUrl
            item.imageUrls.isNotEmpty() -> item.imageUrls.first()
            else -> ""
        }

        ListingCard.bindCover(holder.ivCover, imageUrl)

        holder.btnReview.setOnClickListener {
            onReview(item)
        }

        holder.itemView.setOnClickListener {
            onReview(item)
        }
    }

    override fun getItemCount(): Int = items.size

    fun replaceAll(newItems: List<Property>) {
        items.clear()
        items.addAll(newItems)
        notifyDataSetChanged()
    }
}
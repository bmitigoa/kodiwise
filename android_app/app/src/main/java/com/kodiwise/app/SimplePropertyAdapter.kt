package com.kodiwise.app

import android.content.Context
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.TextView

class SimplePropertyAdapter(
    context: Context,
    private val items: List<SimplePropertyItem>
) : ArrayAdapter<SimplePropertyItem>(context, 0, items) {

    override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
        val view = convertView ?: LayoutInflater.from(context)
            .inflate(android.R.layout.simple_list_item_2, parent, false)

        val item = items[position]
        view.findViewById<TextView>(android.R.id.text1).text = item.title
        view.findViewById<TextView>(android.R.id.text2).text = item.location
        return view
    }
}
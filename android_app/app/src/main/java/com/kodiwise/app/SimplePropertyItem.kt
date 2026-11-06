package com.kodiwise.app

data class SimplePropertyItem(
    val id: String,
    val title: String,
    val location: String,
    val coverImageUrl: String,
    val quotedRent: Int,
    val rentBand: String
)
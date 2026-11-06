package com.kodiwise.app

import com.google.gson.annotations.SerializedName

data class PredictionRequest(

    @SerializedName("bedrooms_num")
    val bedroomsNum: Int,

    @SerializedName("bathrooms_num")
    val bathroomsNum: Int,

    @SerializedName("location_std")
    val locationStd: String,

    @SerializedName("property_type_std")
    val propertyTypeStd: String,

    @SerializedName("title_clean")
    val titleClean: String,

    // optional amenities (defaults = 0)
    @SerializedName("has_backup_water")
    val hasBackupWater: Int = 0,

    @SerializedName("has_borehole")
    val hasBorehole: Int = 0,

    @SerializedName("has_cctv")
    val hasCctv: Int = 0,

    @SerializedName("has_dsq")
    val hasDsq: Int = 0,

    @SerializedName("has_garden")
    val hasGarden: Int = 0,

    @SerializedName("has_generator")
    val hasGenerator: Int = 0,

    @SerializedName("has_play_area")
    val hasPlayArea: Int = 0,

    @SerializedName("is_furnished_page")
    val isFurnishedPage: Int = 0,

    @SerializedName("is_serviced_page")
    val isServicedPage: Int = 0
)
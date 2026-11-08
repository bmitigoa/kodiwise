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

    // Expanded-form fields (Run D / ml.features.RUN_D_FEATURE_SET), read by
    // the new KodiWise API. All optional -- the old v8 API ignores unknown
    // fields, so this stays compatible with both until the URL cutover.
    @SerializedName("sq_m")
    val sqM: Double? = null,

    @SerializedName("is_furnished")
    val isFurnished: Int = 0,

    @SerializedName("property_type")
    val propertyType: String? = null,

    // Optional amenities. null = not given (omitted from the JSON, so the API
    // says "Amenities (not given)"); 0/1 once the user answered.
    @SerializedName("has_backup_water")
    val hasBackupWater: Int? = null,

    @SerializedName("has_borehole")
    val hasBorehole: Int? = null,

    @SerializedName("has_cctv")
    val hasCctv: Int? = null,

    @SerializedName("has_dsq")
    val hasDsq: Int? = null,

    @SerializedName("has_garden")
    val hasGarden: Int? = null,

    @SerializedName("has_generator")
    val hasGenerator: Int? = null,

    @SerializedName("has_play_area")
    val hasPlayArea: Int? = null,

    @SerializedName("is_furnished_page")
    val isFurnishedPage: Int = 0,

    @SerializedName("is_serviced_page")
    val isServicedPage: Int = 0
)
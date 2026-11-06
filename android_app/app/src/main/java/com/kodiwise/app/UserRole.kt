package com.kodiwise.app

enum class UserRole(val key: String) {
    TENANT("tenant"),
    LANDLORD("landlord"),
    ADMIN("admin");

    companion object {
        fun from(value: String?): UserRole {
            return when (value?.lowercase()) {
                "landlord" -> LANDLORD
                "admin" -> ADMIN
                else -> TENANT
            }
        }
    }
}
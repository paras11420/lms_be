from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Book, BorrowedBook, Reservation

class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ['username', 'email', 'role', 'is_staff']
    fieldsets = UserAdmin.fieldsets + ((None, {'fields': ('role',)}),)
    add_fieldsets = UserAdmin.add_fieldsets + ((None, {'fields': ('role',)}),)

admin.site.register(User, CustomUserAdmin)

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "isbn", "total_copies", "available_copies")
    search_fields = ("title", "author", "isbn")
    list_filter = ("is_borrowed", "author")

    def total_copies(self, obj):
        return obj.quantity
    total_copies.short_description = 'Total Copies'

    def available_copies(self, obj):
        return obj.available_copies
    available_copies.short_description = 'Available Copies'

@admin.register(BorrowedBook)
class BorrowedBookAdmin(admin.ModelAdmin):
    list_display = ['user', 'book', 'borrowed_at', 'due_date', 'returned_at', 'fine_amount']
    list_filter = ['returned_at']
    search_fields = ['user__username', 'book__title']

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ['user', 'book', 'reserved_at', 'status']
    search_fields = ['user__username', 'book__title']
    list_filter = ['status']
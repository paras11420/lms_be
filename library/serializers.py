from rest_framework import serializers
from django.utils.timezone import now
from django.contrib.auth import get_user_model
from .models import Book, BorrowedBook, Reservation
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role']

class BookSerializer(serializers.ModelSerializer):
    available_copies = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = [
            'id', 'title', 'author', 'isbn', 'cover_image',
            'description', 'category', 'is_borrowed', 'borrowed_by',
            'due_date', 'quantity', 'available_copies'
        ]

    def get_available_copies(self, obj):
        # Return the annotated value if it exists, otherwise fall back to the model's property.
        return getattr(obj, 'annotated_available_copies', obj.available_copies)

class BorrowedBookSerializer(serializers.ModelSerializer):
    book_title = serializers.ReadOnlyField(source="book.title")
    user_name = serializers.ReadOnlyField(source="user.username")
    current_fine = serializers.SerializerMethodField()

    class Meta:
        model = BorrowedBook
        fields = [
            'id', 'user', 'user_name', 'book', 'book_title',
            'borrowed_at', 'due_date', 'returned_at', 'fine_amount',
            'current_fine'
        ]

    def get_current_fine(self, obj):
        """
        Calculate the real-time fine if the book is not returned yet.
        If returned, return the final fine_amount.
        """
        if not obj.returned_at:
            overdue_days = max(0, (now() - obj.due_date).days)
            return overdue_days * 5  # Adjust daily fine as needed
        return float(obj.fine_amount)

class ReservationSerializer(serializers.ModelSerializer):
    book_title = serializers.ReadOnlyField(source="book.title")
    user_name = serializers.ReadOnlyField(source="user.username")

    class Meta:
        model = Reservation
        fields = [
            'id', 'user', 'user_name', 'book', 'book_title',
            'reserved_at', 'status'
        ]

# Custom Token Serializer to include the user's role (and username)
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data['role'] = self.user.role
        data['username'] = self.user.username
        return data

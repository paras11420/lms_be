from django.db import models
from django.utils.timezone import now, timedelta
from django.contrib.auth.models import AbstractUser

def now_plus_14_days():
    return now() + timedelta(days=14)

# Expose default_due_date so migrations can reference it.
default_due_date = now_plus_14_days

class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('librarian', 'Librarian'),
        ('member', 'Member'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')

    def __str__(self):
        return f"{self.username} ({self.role})"

class Book(models.Model):
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255)
    isbn = models.CharField(max_length=13, unique=True)
    # New fields for enhanced book details:
    cover_image = models.ImageField(upload_to="book_covers/", null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    category = models.CharField(max_length=100, null=True, blank=True)
    
    is_borrowed = models.BooleanField(default=False)
    borrowed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return self.title

    @property
    def available_copies(self):
        from .models import BorrowedBook  # local import to avoid circular import issues
        return self.quantity - BorrowedBook.objects.filter(book=self, returned_at__isnull=True).count()

    @property
    def total_copies(self):
        return self.quantity

class BorrowedBook(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    borrowed_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField(default=default_due_date)
    returned_at = models.DateTimeField(null=True, blank=True)
    fine_amount = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)

    def can_borrow(self):
        if not self.pk and self.book.available_copies > 0:
            self.book.quantity -= 1
            self.book.save()
        elif not self.pk:
            raise ValueError("No copies available for borrowing.")

    def return_book(self):
        if not self.returned_at:  # Ensure book is not already returned
            self.returned_at = now()
            overdue_days = max(0, (self.returned_at - self.due_date).days)
            self.fine_amount = overdue_days * 5
            self.book.quantity += 1
            self.book.save()
            super().save(update_fields=['returned_at', 'fine_amount'])

    def clean(self):
        if not self.returned_at:
            self.can_borrow()
        super().clean()

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} borrowed {self.book} (Due: {self.due_date}, Returned: {self.returned_at or 'Not Returned'})"

class Reservation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ]
    book = models.ForeignKey(Book, related_name="reservations", on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    reserved_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Reservation for {self.book.title} by {self.user.username}"

# New Model for Borrow Requests (for notifications and in-dashboard processing)
class BorrowRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    book = models.ForeignKey(Book, related_name="borrow_requests", on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Borrow Request for {self.book.title} by {self.user.username} ({self.status})"

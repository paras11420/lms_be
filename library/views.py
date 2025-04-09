from datetime import timedelta, datetime
from django.shortcuts import get_object_or_404
from django.utils.timezone import now, timezone
from django.db.models import Count, F, ExpressionWrapper, IntegerField, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.views import TokenObtainPairView
import csv
from django.http import HttpResponse

from .models import Book, Reservation, BorrowedBook, BorrowRequest
from .serializers import (
    BookSerializer, ReservationSerializer, UserSerializer,
    MyTokenObtainPairSerializer, BorrowedBookSerializer
)
from library_system.tasks import send_borrow_email

User = get_user_model()

# ------------------------------
# Custom Token View
# ------------------------------
class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

# ------------------------------
# Borrow Book Endpoint
# ------------------------------
class BorrowBookView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, book_id):
        book = get_object_or_404(Book, id=book_id)
        user_role = request.user.role.lower()

        # Librarians can issue books to any user; members only to themselves.
        if user_role == "librarian":
            user_id = request.data.get("user_id")
            if not user_id:
                return Response({"error": "User ID is required for librarians."},
                                status=status.HTTP_400_BAD_REQUEST)
            target_user = get_object_or_404(User, id=user_id)
        else:
            target_user = request.user

        # Check read-only property 'available_copies' to see if any are free
        if book.available_copies <= 0:
            return Response({"message": f"No available copies of '{book.title}'."},
                            status=status.HTTP_400_BAD_REQUEST)

        due_date_str = request.data.get("due_date")
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d") if due_date_str else now() + timedelta(days=14)
        except ValueError:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD."},
                            status=status.HTTP_400_BAD_REQUEST)

        borrowed_book = BorrowedBook.objects.create(
            user=target_user,
            book=book,
            borrowed_at=now(),
            due_date=due_date
        )

        send_borrow_email.apply_async(
            args=[target_user.email, book.title, borrowed_book.due_date.strftime("%Y-%m-%d")]
        )

        return Response({
            "message": f"Book '{book.title}' issued to {target_user.username} successfully!",
            "due_date": borrowed_book.due_date.strftime("%Y-%m-%d")
        }, status=status.HTTP_201_CREATED)

# ------------------------------
# Reserve Book Endpoint
# ------------------------------
class ReserveBookView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, book_id):
        book = get_object_or_404(Book, id=book_id)
        if book.available_copies > 0:
            return Response({
                "message": f"Book '{book.title}' is available for borrowing. Please borrow it instead."
            }, status=status.HTTP_400_BAD_REQUEST)

        reservation = Reservation.objects.create(
            book=book,
            user=request.user,
            status='pending',
            reserved_at=now()
        )

        return Response({
            "message": f"Book '{book.title}' reserved successfully! Your reservation ID: {reservation.id}"
        }, status=status.HTTP_201_CREATED)

# ------------------------------
# Return Book Endpoint
# ------------------------------
class ReturnBookView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, borrowed_book_id):
        if request.user.role.lower() not in ["librarian", "admin"]:
            return Response(
                {"detail": "Only librarians or admins can return books. Please contact your librarian for assistance."},
                status=status.HTTP_403_FORBIDDEN
            )

        borrowed_book = get_object_or_404(BorrowedBook, id=borrowed_book_id)
        if borrowed_book.returned_at is not None:
            return Response({"message": "Book already returned."},
                            status=status.HTTP_400_BAD_REQUEST)

        borrowed_book.return_book()
        return Response({
            "message": f"Book '{borrowed_book.book.title}' returned successfully! Fine: {borrowed_book.fine_amount}"
        })

# ------------------------------
# Borrowed Books View
# ------------------------------
class BorrowedBooksView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role.lower() == "librarian":
            borrowed_books = BorrowedBook.objects.filter(returned_at__isnull=True)
        else:
            borrowed_books = BorrowedBook.objects.filter(user=request.user, returned_at__isnull=True)
        serializer = BorrowedBookSerializer(borrowed_books, many=True)
        return Response({"borrowed_books": serializer.data})

# ------------------------------
# Book List & Create
# ------------------------------
class BookListView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        # Only return books with quantity > 0
        books = Book.objects.filter(quantity__gt=0)
        serializer = BookSerializer(books, many=True)
        return Response({"available_books": serializer.data})

    def post(self, request):
        if not request.user.is_authenticated or request.user.role.lower() not in ["librarian", "admin"]:
            return Response({"detail": "Not authorized."},
                            status=status.HTTP_403_FORBIDDEN)

        serializer = BookSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# ------------------------------
# Book Detail, Update, & Delete
# ------------------------------
class BookDetailView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, book_id):
        book = get_object_or_404(Book, id=book_id)
        serializer = BookSerializer(book)
        return Response({"book": serializer.data})

    def put(self, request, book_id):
        if not request.user.is_authenticated or request.user.role.lower() not in ["librarian", "admin"]:
            return Response({"detail": "Not authorized."},
                            status=status.HTTP_403_FORBIDDEN)

        book = get_object_or_404(Book, id=book_id)
        serializer = BookSerializer(book, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, book_id):
        if not request.user.is_authenticated or request.user.role.lower() not in ["librarian", "admin"]:
            return Response({"detail": "Not authorized."},
                            status=status.HTTP_403_FORBIDDEN)
        book = get_object_or_404(Book, id=book_id)
        book.delete()
        return Response({"message": "Book deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

# ------------------------------
# User Reservations
# ------------------------------
class UserReservationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        reservations = Reservation.objects.filter(user=request.user)
        serializer = ReservationSerializer(reservations, many=True)
        return Response({"reservations": serializer.data})

# ------------------------------
# Book Search
# ------------------------------
class BookSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        title = request.GET.get('title', '')
        author = request.GET.get('author', '')
        isbn = request.GET.get('isbn', '')
        books = Book.objects.filter(
            title__icontains=title,
            author__icontains=author,
            isbn__icontains=isbn
        )
        serializer = BookSerializer(books, many=True)
        return Response({"books": serializer.data})

# ------------------------------
# Dashboard
# ------------------------------
class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        total_books = Book.objects.count()
        borrowed_books = BorrowedBook.objects.filter(returned_at__isnull=True).count()
        overdue_books = BorrowedBook.objects.filter(
            returned_at__isnull=True, due_date__lt=now()
        ).count()

        # Annotate available copies
        books_with_availability = Book.objects.annotate(
            borrowed_count=Count('borrowedbook', filter=Q(borrowedbook__returned_at__isnull=True))
        ).annotate(
            annotated_available_copies=ExpressionWrapper(
                F('quantity') - F('borrowed_count'),
                output_field=IntegerField()
            )
        )

        # "Most Borrowed Books": order by lowest annotated available copies
        most_borrowed_books = books_with_availability.order_by('annotated_available_copies')[:5]
        serialized_books = BookSerializer(most_borrowed_books, many=True).data

        # Low availability: books with <= 2 copies left
        low_availability_books = books_with_availability.filter(
            quantity__gt=0,
            annotated_available_copies__lte=2
        )
        low_availability_data = BookSerializer(low_availability_books, many=True).data

        # Pending Borrow Requests
        pending_requests = BorrowRequest.objects.filter(status="pending")
        borrow_requests_data = [{
            "id": req.id,
            "book_title": req.book.title,
            "user": req.user.username,
            "requested_at": req.requested_at
        } for req in pending_requests]

        return Response({
            "total_books": total_books,
            "borrowed_books": borrowed_books,
            "overdue_books": overdue_books,
            "most_borrowed_books": serialized_books,
            "low_availability": low_availability_data,
            "pending_borrow_requests": borrow_requests_data,
        })

# ------------------------------
# Borrow Request
# ------------------------------
class BorrowRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, book_id):
        if BorrowRequest.objects.filter(book_id=book_id, user=request.user, status='pending').exists():
            return Response({"message": "You already have a pending borrow request for this book."},
                            status=status.HTTP_400_BAD_REQUEST)
        borrow_request = BorrowRequest.objects.create(book_id=book_id, user=request.user)
        return Response({"message": f"Borrow request for '{borrow_request.book.title}' submitted successfully."},
                        status=status.HTTP_201_CREATED)

    def put(self, request, request_id):
        if request.user.role.lower() not in ["librarian", "admin"]:
            return Response({"detail": "Not authorized."},
                            status=status.HTTP_403_FORBIDDEN)
        borrow_request = get_object_or_404(BorrowRequest, id=request_id)
        action = request.data.get("action")
        if action == "approve":
            borrowed_book = BorrowedBook.objects.create(
                user=borrow_request.user,
                book=borrow_request.book,
                borrowed_at=now(),
                due_date=now() + timedelta(days=14)
            )
            borrow_request.status = "approved"
            borrow_request.save()
            return Response({
                "message": f"Borrow request approved. Book '{borrow_request.book.title}' issued to {borrow_request.user.username}."
            })
        elif action == "reject":
            borrow_request.status = "rejected"
            borrow_request.save()
            return Response({
                "message": f"Borrow request for '{borrow_request.book.title}' has been rejected."
            })
        else:
            return Response({"error": "Invalid action."},
                            status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    username = request.data.get('username')
    email = request.data.get('email')
    password = request.data.get('password')
    if not username or not email or not password:
        return Response({"error": "All fields are required."},
                        status=status.HTTP_400_BAD_REQUEST)
    user = User.objects.create_user(username=username, email=email, password=password)
    serializer = UserSerializer(user)
    return Response(serializer.data, status=status.HTTP_201_CREATED)

class UserListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role.lower() not in ["librarian", "admin"]:
            return Response({"detail": "Not authorized."},
                            status=status.HTTP_403_FORBIDDEN)
        users = User.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response({"users": serializer.data})

# ------------------------------
# NEW: Reservation Management Endpoints
# ------------------------------
class CancelReservationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, reservation_id):
        reservation = get_object_or_404(Reservation, id=reservation_id)
        if reservation.status != 'pending':
            return Response({"error": "Only pending reservations can be cancelled."},
                            status=status.HTTP_400_BAD_REQUEST)
        reservation.status = 'cancelled'
        reservation.save()
        return Response({"message": "Reservation cancelled successfully."}, status=status.HTTP_200_OK)

class FulfillReservationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, reservation_id):
        reservation = get_object_or_404(Reservation, id=reservation_id)
        book = reservation.book
        # Check read-only property
        if book.available_copies <= 0:
            return Response({"error": "No available copies to fulfill the reservation."},
                            status=status.HTTP_400_BAD_REQUEST)
        # Create BorrowedBook
        borrowed_book = BorrowedBook.objects.create(
            user=reservation.user,
            book=book,
            borrowed_at=now(),
            due_date=now() + timedelta(days=14)
        )
        # Decrement the real field: 'quantity'
        book.quantity -= 1
        book.save()

        reservation.status = 'fulfilled'
        reservation.save()
        return Response({
            "message": "Reservation fulfilled and book issued.",
            "borrowed_book": BorrowedBookSerializer(borrowed_book).data
        }, status=status.HTTP_200_OK)

class ExportReservationsCSVView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        reservations = Reservation.objects.filter(book__id=book_id)
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="reservations_book_{book_id}.csv"'
        writer = csv.writer(response)
        writer.writerow(['User', 'Reserved At', 'Status'])
        for res in reservations:
            writer.writerow([res.user.username, res.reserved_at, res.status])
        return response

# ------------------------------
# UPDATED: Book Reservations (Reservation Queue) with Sorting, Searching, and Pagination
# ------------------------------
class BookReservationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        book = get_object_or_404(Book, id=book_id)
        reservations = Reservation.objects.filter(book=book)
        
        # If user is not librarian/admin, show only their reservation(s)
        if request.user.role.lower() not in ["librarian", "admin"]:
            reservations = reservations.filter(user=request.user)
        
        # Searching
        search_query = request.GET.get('search', '')
        if search_query:
            reservations = reservations.filter(
                Q(user__username__icontains=search_query) |
                Q(status__icontains=search_query)
            )
        
        # Sorting (typo fix: 'orderx_by' -> 'order_by')
        sort_by = request.GET.get('sort', 'reserved_at')
        reservations = reservations.order_by(sort_by)
        
        # Pagination
        paginator = PageNumberPagination()
        paginator.page_size = 10
        paginated_reservations = paginator.paginate_queryset(reservations, request)
        serializer = ReservationSerializer(paginated_reservations, many=True)
        
        return paginator.get_paginated_response({
            "book_title": book.title,
            "reservations": serializer.data
        })

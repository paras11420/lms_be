from celery import shared_task  
from django.core.mail import send_mail, BadHeaderError, EmailMultiAlternatives
from django.conf import settings
from django.utils.timezone import now, timezone
from django.template.loader import render_to_string
from library.models import BorrowedBook, Reservation
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

@shared_task
def send_borrow_email(user_email, book_title, due_date):
    subject = '📚 Book Borrowed Confirmation'
    from_email = settings.DEFAULT_FROM_EMAIL
    to = [user_email]

    try:
        # Optional: extract name from email
        username = user_email.split('@')[0].capitalize()

        # Render HTML template
        html_content = render_to_string('emails/borrow_confirmation.html', {
            'username': username,
            'book_title': book_title,
            'due_date': due_date,
            'return_url': 'http://127.0.0.1:3000/return-book'  # Update if needed
        })

        # Create email message with both plain text and HTML versions
        msg = EmailMultiAlternatives(
            subject, 
            f'You have borrowed "{book_title}". The due date for return is {due_date}.', 
            from_email, 
            to
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()

        logger.info("Borrow confirmation email sent to %s", user_email)
        return f'Borrow confirmation email sent to {user_email}'

    except BadHeaderError:
        logger.error("Invalid header detected for %s", user_email)
        return 'Invalid email header detected'

    except Exception as e:
        logger.error("Error sending email to %s: %s", user_email, str(e))
        return f'Error sending email: {str(e)}'

@shared_task
def send_overdue_notifications():
    overdue_books = BorrowedBook.objects.filter(
        due_date__lt=now(), returned_at__isnull=True
    ).select_related("user", "book")

    count = 0
    for record in overdue_books:
        if record.user and record.user.email:
            subject = 'Overdue Book Reminder'
            message = f'The book "{record.book.title}" is overdue. Please return it as soon as possible.'
            from_email = settings.DEFAULT_FROM_EMAIL
            try:
                send_mail(subject, message, from_email, [record.user.email], fail_silently=False)
                count += 1
            except BadHeaderError:
                logger.warning("Invalid header for email %s", record.user.email)
                continue
            except Exception as e:
                logger.error("Error sending overdue email to %s: %s", record.user.email, str(e))
                continue
    return f'Sent {count} overdue reminders'

@shared_task
def send_due_date_reminders():
    upcoming_due_books = BorrowedBook.objects.filter(
        due_date__date=now().date(), returned_at__isnull=True
    ).select_related("user", "book")

    count = 0
    for record in upcoming_due_books:
        if record.user and record.user.email:
            subject = 'Upcoming Due Date Reminder'
            message = f'The book "{record.book.title}" is due today. Please return it on time to avoid a fine.'
            from_email = settings.DEFAULT_FROM_EMAIL
            try:
                send_mail(subject, message, from_email, [record.user.email], fail_silently=False)
                count += 1
            except BadHeaderError:
                logger.warning("Invalid header for email %s", record.user.email)
                continue
            except Exception as e:
                logger.error("Error sending due date email to %s: %s", record.user.email, str(e))
                continue
    return f'Sent {count} due date reminders'

# ------------------------------
# New Feature: Auto-Cancel Expired Reservations
# ------------------------------
@shared_task
def auto_cancel_expired_reservations():
    """
    Automatically cancel reservations that have been pending for more than a specified period.
    Change 'expiration_period' as needed.
    """
    expiration_period = timedelta(days=3)  # Cancel if pending > 3 days
    expiration_time = now() - expiration_period
    expired_reservations = Reservation.objects.filter(status='pending', reserved_at__lt=expiration_time)
    count = expired_reservations.count()
    expired_reservations.update(status='cancelled')
    logger.info("Auto-cancelled %d expired reservations", count)
    return f'Auto-cancelled {count} expired reservations'

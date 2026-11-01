from django.db import models


class ContactMessage(models.Model):
    """Submissions from the Contact Us enquiry form."""

    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=15, blank=True)
    message = models.TextField(max_length=3000)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} <{self.email}>"


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

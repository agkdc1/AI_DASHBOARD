"""Printer & Tray models for the Invoice Print plugin."""

from django.db import models


class Printer(models.Model):
    name = models.CharField(max_length=255)
    ip = models.GenericIPAddressField()
    platform = models.CharField(
        max_length=20,
        choices=[("yamato", "Yamato B2 Cloud"), ("sagawa", "Sagawa e-Hikari")],
    )
    has_multiple_trays = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "invoice_plugin"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.ip})"


class Tray(models.Model):
    printer = models.ForeignKey(
        Printer, on_delete=models.CASCADE, related_name="trays",
    )
    name = models.CharField(max_length=255)
    paper_size = models.CharField(max_length=50)
    label_type = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "invoice_plugin"
        ordering = ["printer", "name"]

    def __str__(self):
        return f"{self.printer.name} / {self.name}"

"""Create or update an operator account for the /console dashboard.

    python manage.py create_console_user
    python manage.py create_console_user --name "Jane Doe" --phone +256770123456 \
        --email jane@fuelondemand.test --title "Head of Ops" --password "..." --superuser
"""
from __future__ import annotations

import getpass

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from core.models import AuditEvent, User
from core.utils import normalize_phone


class Command(BaseCommand):
    help = "Create (or update) an account that can sign in to the operations console."

    def add_arguments(self, parser):
        parser.add_argument("--name", help="Full name shown in the console")
        parser.add_argument("--phone", help="Phone number, e.g. +256770123456")
        parser.add_argument("--email", default="", help="Optional, also usable as the sign-in identifier")
        parser.add_argument("--title", default="Operations", help="Job title shown in the sidebar")
        parser.add_argument("--password", help="Skip the prompt (careful: it lands in shell history)")
        parser.add_argument("--superuser", action="store_true", help="Also grant Django admin rights")
        parser.add_argument("--update", action="store_true", help="Update the account if the phone already exists")

    def handle(self, *args, **options):
        name = (options["name"] or input("Full name: ")).strip()
        phone = normalize_phone(options["phone"] or input("Phone (+256...): "))
        email = (options["email"] or input("Email (optional): ")).strip()
        title = (options["title"] or "Operations").strip()

        if not name:
            raise CommandError("A name is required.")
        if not phone:
            raise CommandError("A phone number is required.")

        password = options["password"]
        if not password:
            password = getpass.getpass("Password (min 8 characters): ")
            if password != getpass.getpass("Confirm password: "):
                raise CommandError("The passwords did not match.")
        if len(password) < 8:
            raise CommandError("Use a password with at least 8 characters.")

        user = User.objects.filter(phone=phone).first()
        created = user is None
        if user and not options["update"]:
            raise CommandError(f"{phone} already exists. Re-run with --update to reset it.")
        if user is None:
            user = User(phone=phone)

        user.name = name
        user.email = email
        user.role = "staff"
        user.console_title = title
        user.is_staff = True
        user.is_console_user = True
        user.is_active = True
        user.is_suspended = False
        if options["superuser"]:
            user.is_superuser = True
        user.set_password(password)

        try:
            user.full_clean(exclude=["password"])
        except ValidationError as exc:
            raise CommandError("; ".join(f"{field}: {' '.join(msgs)}" for field, msgs in exc.message_dict.items()))
        user.save()

        AuditEvent.objects.create(
            actor=user,
            action="console.account_created" if created else "console.account_updated",
            target=user.email or user.phone,
            severity=AuditEvent.Severity.INFO,
            meta={"title": title, "superuser": bool(options["superuser"])},
            user_agent="manage.py create_console_user",
        )

        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} console operator: {user.name} <{user.phone}>"))
        self.stdout.write(f"  Sign-in identifier: {user.email or user.phone}")
        self.stdout.write(f"  Also accepts:       {user.phone}")
        self.stdout.write(f"  Console:            http://127.0.0.1:8000/console/")
        if user.is_superuser:
            self.stdout.write("  Django admin:       http://127.0.0.1:8000/admin/")

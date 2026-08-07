from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Contact
from database.validators import verify_email_domain_exists


class ContactRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_name(self, user_id: int, name: str) -> Contact | None:
        """
        Busca un contacto por nombre (búsqueda insensible a mayúsculas/minúsculas).
        Si el contacto ya está guardado en la BD, se asume que fue previamente verificado y existe.
        """
        clean_name = name.strip().lower()
        stmt = select(Contact).where(
            Contact.user_id == user_id,
            Contact.name.ilike(f"%{clean_name}%"),
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def save_or_update(self, user_id: int, name: str, email: str) -> Contact | None:
        """
        Guarda un nuevo contacto o actualiza su email si ya existe el nombre.
        IMPORTANTE: Verifica que la cuenta/dominio exista realmente ANTES de guardar en la BD.
        """
        valid = await verify_email_domain_exists(email)
        if not valid:
            return None

        existing = await self.get_by_name(user_id, name)
        if existing:
            existing.email = email.strip()
            existing.name = name.strip()
            await self.session.flush()
            return existing

        contact = Contact(
            user_id=user_id,
            name=name.strip(),
            email=email.strip(),
        )
        self.session.add(contact)
        await self.session.flush()
        return contact

    async def list_contacts(self, user_id: int) -> list[Contact]:
        """Lista todos los contactos guardados del usuario."""
        stmt = select(Contact).where(Contact.user_id == user_id).order_by(Contact.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def clean_dummy_contacts(self) -> int:
        """Elimina cualquier contacto guardado con emails de ejemplo o ficticios."""
        stmt = delete(Contact).where(
            (Contact.email.ilike("%@example.%")) |
            (Contact.email.ilike("%@test.%")) |
            (Contact.email.ilike("%@domain.%"))
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount



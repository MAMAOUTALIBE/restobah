"""Sequence regressions use only Django's temporary test database."""
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TransactionTestCase

from .models import Category, Product, Restaurant


class SeedSequenceTests(TransactionTestCase):
    reset_sequences = True

    def seed(self):
        call_command('seed_demo', stdout=StringIO())

    def repair(self):
        call_command('repair_crm_sequences', stdout=StringIO())

    def new_product(self, **extra):
        return Product.objects.create(
            name='Plat ajouté après initialisation',
            category=Category.objects.first(),
            description='Une recette du restaurant.',
            price=Decimal('7.50'),
            **extra,
        )

    def test_seed_then_automatic_ids_do_not_collide_for_products_or_restaurant(self):
        self.seed()
        self.assertGreater(self.new_product().pk, 90)
        self.assertGreater(Restaurant.objects.create(name='Périmètre de test', delivery_enabled=False).pk, 1)

    def test_repeated_seed_preserves_customized_recipes_and_settings(self):
        self.seed()
        Product.objects.filter(pk=1).update(name='Ma recette', price=Decimal('17.20'), available=False)
        Restaurant.objects.filter(pk=1).update(name='Mon restaurant', ordering_enabled=False)
        custom = self.new_product()
        self.seed()
        product = Product.objects.get(pk=1)
        restaurant = Restaurant.objects.get(pk=1)
        self.assertEqual((product.name, product.price, product.available), ('Ma recette', Decimal('17.20'), False))
        self.assertEqual((restaurant.name, restaurant.ordering_enabled), ('Mon restaurant', False))
        self.assertTrue(Product.objects.filter(pk=custom.pk).exists())
        self.assertGreater(self.new_product().pk, custom.pk)

    def test_repair_existing_explicit_ids_without_loading_demo_data(self):
        Restaurant.objects.create(pk=1, name='Restaurant existant', delivery_enabled=False)
        Category.objects.create(name='Catégorie existante')
        self.new_product(pk=90)
        self.repair()
        self.assertEqual(Product.objects.count(), 1)
        self.assertGreater(self.new_product().pk, 90)
        self.assertGreater(Restaurant.objects.create(name='Périmètre de test', delivery_enabled=False).pk, 1)

    def test_repair_without_reseed_never_rewinds_or_recreates_deleted_recipes(self):
        self.seed()
        high_product = self.new_product()
        product_id = high_product.pk
        high_product.delete()
        Product.objects.filter(pk=6).delete()
        high_restaurant = Restaurant.objects.create(name='Périmètre de test', delivery_enabled=False)
        restaurant_id = high_restaurant.pk
        high_restaurant.delete()
        before = list(Product.objects.order_by('pk').values())
        settings = Restaurant.objects.values().get(pk=1)
        self.repair()
        self.repair()
        self.assertEqual(list(Product.objects.order_by('pk').values()), before)
        self.assertEqual(Restaurant.objects.values().get(pk=1), settings)
        self.assertFalse(Product.objects.filter(pk=6).exists())
        self.assertGreater(self.new_product().pk, product_id)
        self.assertGreater(Restaurant.objects.create(name='Autre périmètre', delivery_enabled=False).pk, restaurant_id)

    def test_repair_empty_tables_does_not_allocate_an_id(self):
        self.repair()
        self.assertEqual(Restaurant.objects.count(), 0)
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(Restaurant.objects.create(name='Premier restaurant', delivery_enabled=False).pk, 1)
        category = Category.objects.create(name='Première catégorie')
        self.assertEqual(self.new_product().pk, 1)
        self.assertEqual(Product.objects.get(pk=1).category_id, category.pk)

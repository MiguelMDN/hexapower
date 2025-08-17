# Auditoría de importaciones Dolibarr

- Fecha: 2025-08-16
- Usuario: MiguelMDN

## Lotes registrados

1) 20250816225637 — Productos (produit_1_min.csv)
- Tabla: llx_product
- Consultas:
  ```sql
  SELECT rowid, ref, label FROM llx_product WHERE import_key='20250816225637';
  SELECT COUNT(*) FROM llx_product WHERE import_key='20250816225637';
  ```
- Reversión segura (no borra históricos):
  ```sql
  UPDATE llx_product
  SET tosell = 0, tobuy = 0
  WHERE import_key = '20250816225637';
  ```

2) 20250816230356 — Multiprecios (produit_multiprice_min.csv)
- Tabla: llx_product_price
- Consultas:
  ```sql
  SELECT rowid, fk_product, price, price_level, date_price
  FROM llx_product_price
  WHERE import_key='20250816230356';

  SELECT COUNT(*)
  FROM llx_product_price
  WHERE import_key='20250816230356';
  ```
- Reversión:
  ```sql
  DELETE FROM llx_product_price WHERE import_key='20250816230356';
  ```

3) 20250816230916 — Precios de proveedores (produit_supplierprice_min.csv)
- Tabla: llx_product_fournisseur_price
- Consultas:
  ```sql
  SELECT rowid, fk_product, fk_soc, ref_fourn, unitprice, quantity
  FROM llx_product_fournisseur_price
  WHERE import_key='20250816230916';

  SELECT COUNT(*)
  FROM llx_product_fournisseur_price
  WHERE import_key='20250816230916';
  ```
- Reversión:
  ```sql
  DELETE FROM llx_product_fournisseur_price WHERE import_key='20250816230916';
  ```

## Notas
- CSV con separador ; y comillas ".
- Fechas en formato YYYY-MM-DD.
- Recomendación para cambios masivos:
  ```sql
  START TRANSACTION;
  -- SELECT para verificar
  -- DELETE/UPDATE según corresponda
  COMMIT; -- o ROLLBACK si algo no coincide
  ```

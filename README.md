## file_det
| cid | name               | type    | notnull | dflt_value | pk |
|-----|--------------------|---------|---------|------------|----|
| 0   | gyujto            | TEXT    | 0       |            | 0  |
| 1   | nyilvanossagjelolo | TEXT    | 0       |            | 0  |
| 2   | dateLastModified  | TEXT    | 0       |            | 0  |
| 3   | statetext         | TEXT    | 0       |            | 0  |
| 4   | name              | TEXT    | 0       |            | 0  |
| 5   | userLastModified  | TEXT    | 0       |            | 0  |
| 6   | filesize          | INTEGER | 0       |            | 0  |
| 7   | uuid              | TEXT    | 1       |            | 0  |
| 8   | agenda_uuid       | TEXT    | 0       |            | 0  |
| 9   | folder_uuid       | TEXT    | 0       |            | 0  |

## meghivo_mappa
| cid | name               | type | notnull | dflt_value | pk |
|-----|--------------------|------|---------|------------|----|
| 0   | folder_uuid       | TEXT | 0       |            | 0  |
| 1   | detail_uuid       | TEXT | 0       |            | 0  |
| 2   | datum             | TEXT | 0       |            | 0  |
| 3   | name              | TEXT | 0       |            | 0  |
| 4   | testuletijelolo   | TEXT | 0       |            | 0  |
| 5   | targy             | TEXT | 0       |            | 0  |
| 6   | napirend          | TEXT | 0       |            | 0  |
| 7   | kategoria         | TEXT | 0       |            | 0  |
| 8   | nyilvanossagjelolo | TEXT | 0       |            | 0  |
| 9   | idopont           | TEXT | 0       |            | 0  |
| 10  | hely              | TEXT | 0       |            | 0  |
| 11  | gyujto            | TEXT | 0       |            | 0  |
| 12  | folapra           | TEXT | 0       |            | 0  |
| 13  | eloterjeszto      | TEXT | 0       |            | 0  |
| 14  | dateLastModified  | TEXT | 0       |            | 0  |
| 15  | iktatoszam        | TEXT | 0       |            | 0  |

## napirendi
| cid | name               | type | notnull | dflt_value | pk |
|-----|--------------------|------|---------|------------|----|
| 0   | uuid              | TEXT | 0       |            | 1  |
| 1   | folder_uuid       | TEXT | 0       |            | 0  |
| 2   | gyujto            | TEXT | 0       |            | 0  |
| 3   | targy             | TEXT | 0       |            | 0  |
| 4   | name              | TEXT | 0       |            | 0  |
| 5   | linkName          | TEXT | 0       |            | 0  |
| 6   | napirend          | TEXT | 0       |            | 0  |
| 7   | nyilvanossagjelolo | TEXT | 0       |            | 0  |
| 8   | hasPermissions    | TEXT | 0       |            | 0  |
| 9   | folapra           | TEXT | 0       |            | 0  |
| 10  | eloterjeszto      | TEXT | 0       |            | 0  |
| 11  | referencia        | TEXT | 0       |            | 0  |


---
name: project-docs-updater
description: >
  Skill dung khi agent vua thuc hien code changes tren du an SDLC Agent Platform.
  Huong dan cach cap nhat tai lieu tuong ung chinh xac va day du,
  bao gom ARCHITECTURE.md, DATABASE.md, API.md, FLOWS.md, BUGS.md, CHANGELOG.md
  va tao ADR moi khi can. Trigger khi: sau khi sua code, fix bug, them feature, thay doi DB schema.
---

# Skill: Project Documentation Updater

## Muc dich

Dam bao tai lieu du an luon dong bo voi code sau moi thay doi.

---

## Checklist cap nhat tai lieu

### Buoc 1: Xac dinh loai thay doi

| Loai thay doi | Files can update |
|---|---|
| Them/sua database table/column/index | .agents/docs/DATABASE.md |
| Them/sua REST API endpoint | .agents/docs/API.md |
| Them/sua module, thay doi dep injection | .agents/docs/ARCHITECTURE.md |
| Them/sua business flow, state machine | .agents/docs/FLOWS.md |
| Fix bug quan trong | .agents/docs/BUGS.md |
| Phat hien bug moi | .agents/docs/BUGS.md |
| Quyet dinh kien truc quan trong | .agents/docs/adr/ADR-NNN.md (moi) |
| Bat ky thay doi dang ke | .agents/docs/CHANGELOG.md |

### Buoc 2: Cap nhat DATABASE.md

Khi them/sua table:
- Ghi day du: ten column, type, nullable, default, constraint
- Ghi indexes moi
- Them migration vao bang Migrations o cuoi file
- Cap nhat dong "Cap nhat lan cuoi"

### Buoc 3: Cap nhat API.md

Khi them/sua endpoint:
- Method + path
- Request body (voi schema)
- Response (voi schema)
- Error status codes co the tra ve

### Buoc 4: Cap nhat ARCHITECTURE.md

Khi them module moi hoac thay doi major:
- Them section trong Module map
- Cap nhat so do ASCII neu data flow thay doi
- Cap nhat bang Environment variables neu them env var moi

### Buoc 5: Cap nhat FLOWS.md

Khi thay doi business logic:
- State machine transitions
- Them flow moi thanh Flow section rieng biet

### Buoc 6: Cap nhat BUGS.md

Khi FIX bug:
```
Doi status: OPEN/INVESTIGATING -> FIXED
Them: Root cause (neu chua co)
Them: Fix: mo ta cach da fix
```

Khi PHAT HIEN bug moi, them entry theo format:
```
## BUG-NNN -- [Ten ngan gon]

- Status: OPEN
- Severity: CRITICAL | HIGH | MEDIUM | LOW
- Module: ten module
- Mo ta: ...
- Root cause: ... (neu biet)
- Fix: chua co
- Discovered: YYYY-MM-DD
```

### Buoc 7: Cap nhat CHANGELOG.md

Them entry LEN DAU file (newest first):
```
## YYYY-MM-DD -- Mo ta ngan thay doi

- Chi tiet thay doi 1
- Chi tiet thay doi 2
- Bug da fix (neu co)
```

### Buoc 8: Tao ADR (neu can)

Tao ADR moi tai .agents/docs/adr/ADR-NNN-ten-kebab-case.md khi:
- Chon technology hoac library moi
- Thay doi pattern kien truc dang ke  
- Quyet dinh tu choi mot approach (rejected alternative)
- Thay doi cach LLM duoc goi (model, streaming, JSON mode...)

Dung template tu: .agents/docs/adr/ADR-000-template.md

---

## Quy tac biet quan trong

1. **Khong xoa lich su**: BUGS.md giu nguyen entries FIXED. CHANGELOG khong xoa entries cu.
2. **Cap nhat "ngay cuoi"**: Moi file doc duoc sua phai cap nhat dong "Cap nhat lan cuoi: YYYY-MM-DD"
3. **Tai lieu truoc, code sau**: Neu task lon, plan tai lieu update truoc roi moi code
4. **Cross-reference**: Neu bug duoc nhan ra la ket qua cua quyet dinh ADR, them ghi chu trong ca hai files

---

## Bao cao sau khi hoan thanh

Sau khi cap nhat tai lieu, bao cao ro rang:
1. List cac files .md da duoc cap nhat
2. ADR moi tao (neu co): ADR-NNN
3. Open questions con lai can clarification tu user

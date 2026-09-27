// pnpm check — asserts on real texts from the database (Penal Code, Sexual Offences Act, judgment titles).
import assert from 'node:assert/strict'
import { caseName, locator, structure, tidySpaces } from './text.ts'

assert.equal(tidySpaces('Act ( Cap. 245 ) and [Act No. 10 of 1969 , Sch.]'), 'Act (Cap. 245) and [Act No. 10 of 1969, Sch.]')
assert.equal(tidySpaces('Article 33 (2) (a)- (d ) of the Constitution .'), 'Article 33 (2) (a)- (d) of the Constitution.')

const s8 = structure(
  '(1) A person who commits an act which causes penetration with a child is guilty of an offence termed defilement. ' +
    '(2) A person who commits an offence of defilement with a child aged eleven years or less shall upon conviction be ' +
    'sentenced to imprisonment for life. (5) It is a defence to a charge under this section if– (a) it is proved that such ' +
    'child, deceived the accused person; and (b) the accused reasonably believed that the child was over the age of eighteen ' +
    'years. (6) The belief referred to in subsection (5)(b) is to be determined having regard to all the circumstances.',
)
assert.deepEqual(
  s8.clauses.map((c) => [c.level, c.label]),
  [[1, '(1)'], [1, '(2)'], [1, '(5)'], [2, '(a)'], [2, '(b)'], [1, '(6)']],
)
assert.ok(s8.clauses[5].text.includes('subsection (5)(b)'), 'cross-references stay inline')

// (i) after (h) is a letter; (i) after a letter that isn't (h) is a roman numeral
const r = structure('Intro: (g) one; (h) two; (i) three; (j) four: (i) sub; (ii) sub.')
assert.deepEqual(r.clauses.map((c) => c.level), [0, 2, 2, 2, 2, 3, 3])

const n = structure('Any person who carries on business, or personally works for gain. [Act No. 10 of 1969 , Sch.]')
assert.deepEqual(n.notes, ['Act No. 10 of 1969, Sch.'])
assert.equal(n.clauses[0].text, 'Any person who carries on business, or personally works for gain.')
assert.equal(structure('[Deleted by Act No. 5 of 2003, s. 2.]').clauses[0].text, '[Deleted by Act No. 5 of 2003, s. 2.]')

assert.equal(caseName('REPUBLIC v DANIEL MUSYOKA MUASYA & 2 others [2010] KEHC 231 (KLR)'), 'Republic v Daniel Musyoka Muasya & 2 others')
assert.equal(caseName('GODFREY NGOTHO MUTISO v REPUBLIC (Criminal Appeal 17 of 2008) [2010] KECA 487'), 'Godfrey Ngotho Mutiso v Republic')
assert.equal(
  caseName('EG & 7 others v Attorney General; DKM & 9 others (Interested Parties) [2019] KEHC 11288 (KLR)'),
  'EG & 7 others v Attorney General',
)
assert.equal(caseName('Stephen M’Riungi, & 3 others vs Republic [1983] KECA 131 (KLR)'), 'Stephen M’Riungi, & 3 others vs Republic')

assert.equal(locator('112(a); scope_text from 69'), 'para 112(a) (limiting words at para 69)')
assert.equal(locator('Final declarations (i) (paragraphs unnumbered)'), 'final declarations (i)')
assert.equal(locator('27 (see also 32)'), 'para 27 (see also para 32)')
assert.equal(locator('36'), 'para 36')

console.log('text checks passed')

<template>
  <div class="credits">
    <!-- Header -->
    <section class="credits-header">
      <h1>{{ $t('credits.title') }}</h1>
      <p class="credits-subtitle">{{ $t('credits.subtitle') }}</p>
    </section>

    <!-- Citation -->
    <section class="card">
      <h2 class="section-title">{{ $t('credits.citationTitle') }}</h2>
      <blockquote class="citation-block">
        <p>{{ $t('credits.citationText') }}</p>
        <p class="citation-doi">{{ $t('credits.citationDoi') }}</p>
        <p class="citation-pub">{{ $t('credits.citationPublisher') }}</p>
      </blockquote>
      <div class="citation-actions">
        <a href="https://doi.org/10.1093/gigascience/giaa010" target="_blank" rel="noopener noreferrer" class="btn btn-outline">
          <SvgIcon name="eye" :size="14" /> {{ $t('credits.viewOnline') }}
        </a>
        <a href="/papers/prifti2020_gigascience_giaa010.pdf" download class="btn btn-outline">
          <SvgIcon name="upload" :size="14" style="transform:rotate(180deg)" /> {{ $t('credits.downloadPdf') }}
        </a>
        <button class="btn btn-outline" @click="copyBibtex">
          {{ copied ? $t('credits.copiedBibtex') : $t('credits.copyBibtex') }}
        </button>
      </div>
    </section>

    <!-- Funding -->
    <section class="card">
      <h2 class="section-title">{{ $t('credits.fundingTitle') }}</h2>
      <div class="funding-item">
        <div class="funding-header">
          <h3>{{ $t('credits.anrProject') }}</h3>
          <span class="badge badge-ref">{{ $t('credits.anrReference') }}</span>
        </div>
        <p class="funding-fulltitle">{{ $t('credits.anrFullTitle') }}</p>
        <p class="funding-desc">{{ $t('credits.anrDescription') }}</p>
        <div class="funding-facts">
          <span class="pill">{{ $t('credits.anrAmount') }}</span>
          <span class="pill">{{ $t('credits.anrDuration') }}</span>
          <span class="pill">{{ $t('credits.anrPi') }}</span>
        </div>
        <div class="funding-partners">
          <span class="partners-label">{{ $t('credits.anrPartners') }}:</span>
          <span class="pill pill-partner">UMMISCO</span>
          <span class="pill pill-partner">NUTRIOMICS</span>
          <span class="pill pill-partner">LAMSADE</span>
          <span class="pill pill-partner">IBISC</span>
        </div>
      </div>
    </section>

    <!-- Industry Partner -->
    <section class="card">
      <h2 class="section-title">{{ $t('credits.partnerTitle') }}</h2>
      <div class="partner-block">
        <div class="partner-header">
          <h3>{{ $t('credits.gmtName') }}</h3>
          <span class="partner-loc">{{ $t('credits.gmtLocation') }}</span>
        </div>
        <p>{{ $t('credits.gmtDescription') }}</p>
        <div class="partner-links">
          <a href="https://www.gmt.bio" target="_blank" rel="noopener noreferrer" class="btn btn-outline btn-sm">
            {{ $t('credits.gmtWebsite') }}
          </a>
        </div>
      </div>
    </section>

    <!-- Core Team -->
    <section class="card">
      <h2 class="section-title">{{ $t('credits.coreTeamTitle') }}</h2>
      <div class="team-grid">
        <div v-for="m in coreTeam" :key="m.name" class="team-card" :class="{ 'team-lead': m.lead }">
          <div class="team-name">
            {{ m.name }}
            <span v-if="m.lead" class="badge badge-lead">{{ $t('credits.correspondingAuthor') }}</span>
          </div>
          <div class="team-role">{{ m.role }}</div>
          <div class="team-affiliation">{{ m.affiliation }}</div>
          <p class="team-desc">{{ m.desc }}</p>
          <a v-if="m.orcid" :href="'https://orcid.org/' + m.orcid" target="_blank" rel="noopener noreferrer" class="orcid-link">
            ORCID: {{ m.orcid }}
          </a>
        </div>
      </div>

      <h3 class="subsection-title">{{ $t('credits.gpredomicsTeamTitle') }}</h3>
      <div class="team-grid">
        <div v-for="m in rustTeam" :key="m.name" class="team-card">
          <div class="team-name">{{ m.name }}</div>
          <div class="team-role">{{ m.role }}</div>
          <div class="team-affiliation">{{ m.affiliation }}</div>
          <p class="team-desc">{{ m.desc }}</p>
          <a v-if="m.orcid" :href="'https://orcid.org/' + m.orcid" target="_blank" rel="noopener noreferrer" class="orcid-link">
            ORCID: {{ m.orcid }}
          </a>
        </div>
      </div>
    </section>

    <!-- Contributors -->
    <section class="card">
      <h2 class="section-title">{{ $t('credits.contributorsTitle') }}</h2>
      <ul class="contrib-list">
        <li v-for="c in contributors" :key="c.name">
          <strong>{{ c.name }}</strong> &mdash; {{ c.desc }}
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import SvgIcon from '../components/SvgIcon.vue'

const { t } = useI18n()

const bibtex = `@article{prifti2020interpretable,
  title={Interpretable and accurate prediction models for metagenomics data},
  author={Prifti, Edi and Chevaleyre, Yann and Hanczar, Blaise and Belda, Eugeni and Danchin, Antoine and Cl{\\'{e}}ment, Karine and Zucker, Jean-Daniel},
  journal={GigaScience},
  volume={9},
  number={3},
  pages={giaa010},
  year={2020},
  publisher={Oxford University Press},
  doi={10.1093/gigascience/giaa010}
}`

const copied = ref(false)

function copyBibtex() {
  navigator.clipboard.writeText(bibtex)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

const coreTeam = computed(() => [
  {
    name: 'Edi Prifti',
    role: t('credits.roleCreator'),
    affiliation: 'IRD',
    desc: t('credits.roleCreatorDesc'),
    orcid: '0000-0001-8861-1305',
    lead: true,
  },
  {
    name: 'Jean-Daniel Zucker',
    role: t('credits.roleCoCreator'),
    affiliation: 'IRD / UMMISCO',
    desc: t('credits.roleCoCreatorDesc'),
    orcid: '0000-0002-5597-7922',
  },
  {
    name: 'Yann Chevaleyre',
    role: t('credits.roleChevaleyre'),
    affiliation: 'LIPN',
    desc: t('credits.roleChevaleyreDesc'),
  },
  {
    name: 'Blaise Hanczar',
    role: t('credits.roleHanczar'),
    affiliation: 'IBISC',
    desc: t('credits.roleHanczarDesc'),
  },
  {
    name: 'Eugeni Belda',
    role: t('credits.roleBelda'),
    affiliation: 'IRD',
    desc: t('credits.roleBeldaDesc'),
    orcid: '0000-0003-4307-5072',
  },
])

const rustTeam = computed(() => [
  {
    name: 'Louison Lesage',
    role: t('credits.roleLesage'),
    affiliation: 'GMT Science',
    desc: t('credits.roleLesageDesc'),
    orcid: '0009-0000-0252-6311',
  },
  {
    name: 'Raynald de Lahondès',
    role: t('credits.roleLahondes'),
    affiliation: 'GMT Science',
    desc: t('credits.roleLahondesDesc'),
    orcid: '0009-0000-2862-9589',
  },
  {
    name: 'Vadim Puller',
    role: t('credits.rolePuller'),
    affiliation: 'GMT Science',
    desc: t('credits.rolePullerDesc'),
    orcid: '0000-0002-3900-8283',
  },
])

const contributors = computed(() => [
  { name: 'Lucas Robin', desc: t('credits.roleRobin') },
  { name: 'Shasha Cui', desc: t('credits.roleCui') },
  { name: 'Magali Cousin Thorez', desc: t('credits.roleCousin') },
  { name: 'Youcef Sklab', desc: t('credits.roleSklab') },
  { name: 'Gaspar Roy', desc: t('credits.roleRoy') },
  { name: 'Fabien Kambu', desc: t('credits.roleKambu') },
])
</script>

<style scoped>
.credits {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 1rem 3rem;
}

.credits-header {
  text-align: center;
  padding: 2.5rem 0 1.5rem;
}

.credits-header h1 {
  font-size: 2rem;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.credits-subtitle {
  color: var(--text-secondary);
  font-size: 1.05rem;
  max-width: 600px;
  margin: 0 auto;
}

.card {
  background: var(--bg-card);
  border-radius: var(--card-radius);
  box-shadow: var(--card-shadow);
  padding: 1.75rem;
  margin-bottom: 1.25rem;
}

.section-title {
  font-size: 1.15rem;
  color: var(--text-primary);
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid var(--border-lighter);
}

.subsection-title {
  font-size: 1rem;
  color: var(--text-secondary);
  margin: 1.5rem 0 0.75rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-lighter);
}

/* Citation */
.citation-block {
  border-left: 3px solid var(--brand);
  padding: 1rem 1.25rem;
  margin: 0 0 1rem;
  background: var(--bg-badge);
  border-radius: 0 8px 8px 0;
  font-size: 0.95rem;
  line-height: 1.6;
  color: var(--text-body);
}

.citation-doi {
  font-weight: 600;
  margin-top: 0.5rem;
  color: var(--text-primary);
}

.citation-pub {
  color: var(--text-muted);
  font-size: 0.85rem;
  margin-top: 0.25rem;
}

.citation-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  text-decoration: none;
  transition: all 0.2s;
}

.btn-outline {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-body);
}

.btn-outline:hover {
  border-color: var(--brand);
  color: var(--brand);
}

.btn-sm {
  padding: 0.35rem 0.75rem;
  font-size: 0.8rem;
}

/* Funding */
.funding-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
  flex-wrap: wrap;
}

.funding-header h3 {
  font-size: 1.1rem;
  color: var(--text-primary);
  margin: 0;
}

.funding-fulltitle {
  font-style: italic;
  color: var(--text-secondary);
  font-size: 0.9rem;
  margin-bottom: 0.75rem;
}

.funding-desc {
  color: var(--text-body);
  font-size: 0.9rem;
  line-height: 1.6;
  margin-bottom: 0.75rem;
}

.funding-facts {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.75rem;
}

.funding-partners {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.partners-label {
  font-size: 0.85rem;
  color: var(--text-secondary);
  font-weight: 600;
}

.badge {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 600;
}

.badge-ref {
  background: var(--badge-dataset);
  color: var(--badge-dataset-text);
}

.badge-lead {
  background: var(--brand);
  color: var(--accent-text);
  font-size: 0.75rem;
  margin-left: 0.5rem;
  vertical-align: middle;
}

.pill {
  display: inline-block;
  padding: 0.25rem 0.65rem;
  border-radius: 16px;
  font-size: 0.8rem;
  background: var(--bg-badge);
  color: var(--text-secondary);
  border: 1px solid var(--border-lighter);
}

.pill-partner {
  background: var(--badge-share);
  color: var(--badge-share-text);
  border: none;
}

/* Partner */
.partner-header {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.partner-header h3 {
  font-size: 1.1rem;
  color: var(--text-primary);
  margin: 0;
}

.partner-loc {
  font-size: 0.85rem;
  color: var(--text-muted);
}

.partner-block p {
  color: var(--text-body);
  font-size: 0.9rem;
  line-height: 1.6;
  margin-bottom: 0.75rem;
}

.partner-links {
  display: flex;
  gap: 0.5rem;
}

/* Team Grid */
.team-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 1rem;
}

.team-card {
  background: var(--bg-badge);
  border-radius: 8px;
  padding: 1rem;
  border: 1px solid var(--border-lighter);
  transition: box-shadow 0.2s;
}

.team-card:hover {
  box-shadow: var(--card-shadow-hover);
}

.team-lead {
  border-top: 3px solid var(--brand);
}

.team-name {
  font-size: 1rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 0.25rem;
}

.team-role {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--brand);
  margin-bottom: 0.15rem;
}

.team-affiliation {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin-bottom: 0.5rem;
}

.team-desc {
  font-size: 0.82rem;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0 0 0.5rem;
}

.orcid-link {
  display: inline-block;
  font-size: 0.75rem;
  color: var(--success-dark);
  text-decoration: none;
  padding: 0.15rem 0.5rem;
  border-radius: 10px;
  background: var(--success-bg);
}

.orcid-link:hover {
  text-decoration: underline;
}

/* Contributors */
.contrib-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.contrib-list li {
  padding: 0.6rem 0;
  border-bottom: 1px solid var(--border-lighter);
  font-size: 0.9rem;
  color: var(--text-body);
  line-height: 1.5;
}

.contrib-list li:last-child {
  border-bottom: none;
}

.contrib-list li strong {
  color: var(--text-primary);
}

@media (max-width: 768px) {
  .credits-header h1 {
    font-size: 1.5rem;
  }

  .team-grid {
    grid-template-columns: 1fr;
  }

  .citation-actions {
    flex-direction: column;
  }

  .citation-actions .btn {
    justify-content: center;
  }
}
</style>

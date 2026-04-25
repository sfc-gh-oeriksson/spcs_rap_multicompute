<template>
  <v-app>
    <v-app-bar app color="primary" dark>
      <v-row align="center" no-gutters>
        <v-col cols="1">
          <v-img
            src="https://upload.wikimedia.org/wikipedia/commons/f/ff/Snowflake_Logo.svg"
            contain :aspect-ratio="184/44" height="40"
          ></v-img>
        </v-col>
        <v-col cols="5" class="text-center">
          <v-toolbar-title>Simple Clerks App</v-toolbar-title>
        </v-col>
        <v-col cols="6" class="d-flex align-center justify-end pr-2">
          <v-chip small class="mr-3 white--text" outlined>
            <v-icon left small>mdi-account</v-icon>
            {{ currentUser || '...' }}
          </v-chip>
          <span class="caption mr-2 white--text">Role:</span>
          <v-btn-toggle v-model="activeRoleIndex" mandatory dense>
            <v-btn
              small
              :color="activeRoleIndex === 0 ? 'white' : 'primary darken-1'"
              :class="activeRoleIndex === 0 ? 'primary--text font-weight-bold' : 'white--text'"
              @click="switchRole('EAP_ROLE1')"
            >
              EAP_ROLE1
            </v-btn>
            <v-btn
              small
              :color="activeRoleIndex === 1 ? 'white' : 'primary darken-1'"
              :class="activeRoleIndex === 1 ? 'primary--text font-weight-bold' : 'white--text'"
              @click="switchRole('EAP_ROLE2')"
            >
              EAP_ROLE2
            </v-btn>
          </v-btn-toggle>
        </v-col>
      </v-row>
    </v-app-bar>

    <v-main>
      <TopClerks :activeRole="currentRole" />
    </v-main>
  </v-app>
</template>

<script>
import axios from 'axios'
import TopClerks from './components/TopClerks'

const ROLES = ['EAP_ROLE1', 'EAP_ROLE2']

export default {
  name: 'App',
  components: { TopClerks },

  data: () => ({
    currentUser: null,
    currentRole: ROLES[0],
    activeRoleIndex: 0,
  }),

  mounted() {
    const baseUrl = process.env.VUE_APP_API_URL
    axios.get(baseUrl + '/whoami')
      .then(r => {
        this.currentUser = r.data.user
        const idx = ROLES.indexOf(r.data.role)
        // Always use one of the allowed roles — session role (e.g. ACCOUNTADMIN)
        // is not passed to the API; the switcher controls the data role.
        this.activeRoleIndex = idx >= 0 ? idx : 0
        this.currentRole = ROLES[this.activeRoleIndex]
      })
      .catch(() => {
        this.currentRole = ROLES[0]
        this.activeRoleIndex = 0
      })
  },

  methods: {
    switchRole(role) {
      this.currentRole = role
      this.activeRoleIndex = ROLES.indexOf(role)
    },
  },
}
</script>

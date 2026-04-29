targetScope = 'resourceGroup'

@description('Deployment location')
param location string = resourceGroup().location

@description('Name prefix for Azure resources')
param namePrefix string = 'cricketcanclubs'

@description('Globally unique App Service name')
param webAppName string = '${namePrefix}-web'

@description('Linux App Service plan name')
param appServicePlanName string = '${namePrefix}-plan'

@description('Python runtime stack')
param pythonVersion string = 'PYTHON|3.11'

var appSettings = [
  {
    name: 'WEBSITES_ENABLE_APP_SERVICE_STORAGE'
    value: 'true'
  }
  {
    name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
    value: 'true'
  }
  {
    name: 'PORT'
    value: '8000'
  }
  {
    name: 'WEBSITES_PORT'
    value: '8000'
  }
  {
    name: 'CRICKETCLUBAPP_DATA_ROOT'
    value: '/home/site/cricketclubapp'
  }
  {
    name: 'CRICKETCLUBAPP_SEED_FILE'
    value: '/home/site/cricketclubapp/seed.json'
  }
  {
    name: 'CRICKETCLUBAPP_DATABASE_FILE'
    value: '/home/site/cricketclubapp/cricketclubapp.db'
  }
  {
    name: 'CRICKETCLUBAPP_CACHE_FILE'
    value: '/home/site/cricketclubapp/store_cache.json'
  }
  {
    name: 'CRICKETCLUBAPP_DASHBOARD_CACHE_FILE'
    value: '/home/site/cricketclubapp/dashboard_cache.json'
  }
  {
    name: 'CRICKETCLUBAPP_UPLOAD_DIR'
    value: '/home/site/cricketclubapp/uploads'
  }
  {
    name: 'CRICKETCLUBAPP_DUPLICATE_DIR'
    value: '/home/site/cricketclubapp/duplicates'
  }
]

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: appServicePlanName
  location: location
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

resource webApp 'Microsoft.Web/sites@2023-12-01' = {
  name: webAppName
  location: location
  kind: 'app,linux'
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      alwaysOn: true
      ftpsState: 'Disabled'
      http20Enabled: true
      minTlsVersion: '1.2'
      linuxFxVersion: pythonVersion
      appCommandLine: 'bash -lc "cd /home/site/wwwroot && ./antenv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"'
      appSettings: appSettings
    }
  }
}

output appServiceName string = webApp.name
output defaultHostName string = webApp.properties.defaultHostName

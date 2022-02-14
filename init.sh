
read -p "Enter the azure storage account key: " storage_key
export AZURE_STORAGE_KEY=$storage_key

read -p "Enter the azure storage account name: " storage_name
export AZURE_STORAGE_ACCOUNT=$storage_name

read -p "Enter the azure container name: " container_name
pulumi login azblob://$container_name

if [ -d "pulumidemo" ]; then
  rm -rf pulumidemo
fi

mkdir pulumidemo

read -p "Enter the passphrase for pulumi: " passphrase
export PULUMI_CONFIG_PASSPHRASE=$passphrase

echo "Done! Now go to pulumidemo and continue."

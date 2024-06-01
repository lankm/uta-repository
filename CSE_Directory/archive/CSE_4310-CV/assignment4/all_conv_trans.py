import torch
from torch import nn
import torch.nn.functional as F
import lightning as L
import torchmetrics
from torchvision import transforms
from torchvision.datasets import Imagenette, CIFAR10
from lightning.pytorch.callbacks.early_stopping import EarlyStopping
from lightning.pytorch.callbacks import ModelCheckpoint
from all_conv_reg import AllConvReg 
import torchvision.models as models


class AllConvTrans(L.LightningModule):
    def __init__(self, num_classes=10):
        super().__init__()

        # load AllConvReg and load it with weights from pretrained imagenette save file
        backbone = AllConvReg()
        backbone.load_state_dict(torch.load('model_weights/all_conv_reg'))

        num_filters = backbone.fc.in_features
        self.feature_extractor = backbone.features # had to change this because self.fc isn't included in children()

        self.classifier = nn.Linear(num_filters, num_classes)

        self.accuracy = torchmetrics.Accuracy(task="multiclass", num_classes=num_classes)

    def forward(self, x):
        # x is a torch tensor with dims ({batch size}, {channels}, {img length}, {img width})
        self.feature_extractor.eval()
        with torch.no_grad():
            representations = self.feature_extractor(x).flatten(1)
        return self.classifier(representations)

    def training_step(self, batch, batch_idx):
        x, y = batch
        y_hat = self(x)
        loss = F.cross_entropy(y_hat, y)

        self.log("train_loss", loss)
        return loss

    def validation_step(self, batch, batch_idx):
        x, y = batch
        y_hat = self(x)
        loss = F.cross_entropy(y_hat, y)

        self.accuracy(y_hat, y)

        self.log("val_accuracy", self.accuracy)
        self.log("val_loss", loss)

    def test_step(self, batch, batch_idx):
        x, y = batch
        y_hat = self(x)
        loss = F.cross_entropy(y_hat, y)

        self.accuracy(y_hat, y)

        self.log("test_accuracy", self.accuracy)
        self.log("test_loss", loss)

    def configure_optimizers(self):
        optimizer = torch.optim.Adam(self.parameters(), lr=1e-3)
        return optimizer
    
def main():
    # Prepare the dataset
    train_transforms = transforms.Compose([
        transforms.CenterCrop(160),
        transforms.Resize(64),
        transforms.RandAugment(),
        transforms.ToTensor(),
        transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2470, 0.2435, 0.2616)),
    ])

    test_transforms = transforms.Compose([
        transforms.CenterCrop(160),
        transforms.Resize(64),
        transforms.ToTensor(),
        transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2470, 0.2435, 0.2616)),
    ])

    # Configure datasets
    train_dataset = CIFAR10("data/cifar10/train/", train=True, download=False, transform=train_transforms)
    test_dataset = CIFAR10("data/cifar10/test/", train=False, download=False, transform=test_transforms)

    # Use 10% of the training set for validation
    train_set_size = int(len(train_dataset) * 0.9)
    val_set_size = len(train_dataset) - train_set_size
    # split training dataset into training and validation sets
    seed = torch.Generator().manual_seed(42)
    train_dataset, val_dataset = torch.utils.data.random_split(train_dataset, [train_set_size, val_set_size], generator=seed)
    val_dataset.dataset.transform = test_transforms

    # Use DataLoader to load the dataset
    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=128, num_workers=8, shuffle=True, persistent_workers=True)
    val_loader =   torch.utils.data.DataLoader(val_dataset, batch_size=128, num_workers=8, shuffle=False, persistent_workers=True)
    test_loader =  torch.utils.data.DataLoader(test_dataset, batch_size=256, num_workers=8, shuffle=False, persistent_workers=True)

    

    # Add EarlyStopping
    early_stop_callback = EarlyStopping(monitor="val_loss", mode="min", patience=3)
    # Configure Checkpoints
    checkpoint_callback = ModelCheckpoint( monitor="val_loss", mode="min")

    model = AllConvTrans()

    # Fit the model
    trainer = L.Trainer(callbacks=[early_stop_callback, checkpoint_callback], max_epochs=-1)
    trainer.fit(model=model, train_dataloaders=train_loader, val_dataloaders=val_loader)

    # Evaluate the model on the test set
    trainer.test(model=model, dataloaders=test_loader)

    torch.save(model.state_dict(), 'model_weights/all_conv_trans')

if __name__ == "__main__":
    main()
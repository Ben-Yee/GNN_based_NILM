import networkx as nx
import pandas as pd
import torch
import torch_geometric
from torch_geometric.data import Dataset, Data
import numpy as np
import os
from tqdm import tqdm

print(f"Torch version: {torch.__version__}")
print(f"Cuda available: {torch.cuda.is_available()}")
print(f"Torch geometric version: {torch_geometric.__version__}")

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from torch_geometric.transforms import RandomLinkSplit, RandomNodeSplit
import torch
from torch.nn import Linear
from torch_geometric.nn import GCNConv
import torch.nn.functional as F
import math


class NilmDataset(Dataset):
    def __init__(self, root, filename, window, sigma, test=False, transform=None, pre_transform=None):
        """2
        root = Where the dataset should be stored. This folder is split
        into raw_dir (downloaded dataset) and processed_dir (processed data).
        """
        self.test = test
        self.filename = filename
        self.window = window
        self.sigma = sigma
        super(NilmDataset, self).__init__(root, transform, pre_transform)

    @property
    def raw_file_names(self):
        """ If this file exists in raw_dir, the download is not triggered.
            (The download func. is not implemented here)
        """
        return [self.filename]

    @property
    def processed_file_names(self):
        """ If these files are found in raw_dir, processing is skipped"""
        data = pd.read_csv(self.raw_paths[0]).reset_index()
        if self.test:
            return [f'data_test_{i}.pt' for i in list(data.index)]
        else:
            return [f'data_{i}.pt' for i in list(data.index)]

    def download(self):
        pass

    def process(self):
        idx = 0
        for raw_path in self.raw_paths:
            appliance = pd.read_csv(raw_path).reset_index()
            main_val = appliance['dishwaser_20'].values  # get only readings
            data_vec = main_val
            adjacency, drift = self._get_adjacency_info(data_vec)
            edge_indices = self._to_edge_index(adjacency)

            # node_feats = np.asarray(drift)
            # node_feats = node_feats.reshape((-1, 1))
            # node_feats = torch.tensor(node_feats, dtype=torch.float)
            labels = np.asarray(drift)
            labels = torch.tensor(labels, dtype=torch.int64)

            data = Data(edge_index=edge_indices, y=labels,
                        #  train_mask=[2000], test_mask=[2000]
                        )
            if self.pre_filter is not None and not self.pre_filter(data):
                continue

            if self.pre_transform is not None:
                data = self.pre_transform(data)

            if self.test:
                torch.save(data, os.path.join(self.processed_dir, f'data_test_{idx}.pt'))
            else:
                torch.save(data, os.path.join(self.processed_dir, f'data_{idx}.pt'))
            idx += 1

    def _get_node_features(self, graph):
        """
        This will return a matrix / 2d array of the shape
        [Number of Nodes, Node Feature size]

        We could also use torch_geometric.from_networkx to create a Data object
        with both adjacency and features, but instead we do it manually here
        """
        all_node_feats = list(nx.get_node_attributes(graph, 'drift').values())

        all_node_feats = np.asarray(all_node_feats)
        all_node_feats = all_node_feats.reshape((-1, 1))
        return torch.tensor(all_node_feats, dtype=torch.float)

    def _get_adjacency_info(self, data_vec):
        data_aggr = []

        for k in range(0, int(np.floor(len(data_vec) / self.window))):
            data_aggr.append(np.mean(data_vec[k * self.window:((k + 1) * self.window)]))

        if (len(data_vec) % self.window > 0):
            data_aggr.append(np.mean(data_vec[int(np.floor(len(data_vec) / self.window)) * self.window:]))
        delta_p = [np.round(data_aggr[i + 1] - data_aggr[i], 2) for i in range(0, len(data_aggr) - 1)]
        Am = np.zeros((len(delta_p), len(delta_p)))
        for i in range(0, Am.shape[0]):
            for j in range(0, Am.shape[1]):
                Am[i, j] = math.exp(-((delta_p[i] - delta_p[j]) / self.sigma) ** 2)
        Am = np.where(Am >= 0.5, 1, 0)
        return Am, delta_p

    def _to_edge_index(self, adjacency):

        edge_indices = []
        for i in range(0, adjacency.shape[0]):
            for j in range(i, adjacency.shape[0]):
                if adjacency[i, j] != 0.0:
                    edge_indices += [[i, j], [j, i]]

        edge_indices = torch.tensor(edge_indices)
        edge_indices = edge_indices.t().to(torch.long).view(2, -1)

        return edge_indices

    def len(self):
        return len(self.processed_file_names)

    def get(self, idx):
        """ - Equivalent to __getitem__ in pytorch
            - Is not needed for PyG's InMemoryDataset
        """
        if self.test:
            data = torch.load(os.path.join(self.processed_dir, f'data_test_{idx}.pt'))
        else:
            data = torch.load(os.path.join(self.processed_dir, f'data_{idx}.pt'))
        return data


def main():
    dataset = NilmDataset(root='data', filename='dishwasher.csv', window=20, sigma=20)
    data = dataset[0]
    degrees = torch_geometric.utils.degree(index=data.edge_index[0])
    data.x = degrees
    print(data)


if __name__ == '__main__':
    main()

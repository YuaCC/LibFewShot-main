# -*- coding: utf-8 -*-
"""
@inproceedings{DBLP:conf/nips/SnellSZ17,
  author    = {Jake Snell and
               Kevin Swersky and
               Richard S. Zemel},
  title     = {Prototypical Networks for Few-shot Learning},
  booktitle = {Advances in Neural Information Processing Systems 30: Annual Conference
               on Neural Information Processing Systems 2017, December 4-9, 2017,
               Long Beach, CA, {USA}},
  pages     = {4077--4087},
  year      = {2017},
  url       = {https://proceedings.neurips.cc/paper/2017/hash/cb8da6767461f2812ae4290eac7cbc42-Abstract.html}
}
https://arxiv.org/abs/1703.05175

Adapted from https://github.com/orobix/Prototypical-Networks-for-Few-shot-Learning-PyTorch.
"""
import torch
import torch.nn.functional as F
from torch import nn

from core.utils import accuracy
from .metric_model import MetricModel


class ProtoLayer(nn.Module):
    def __init__(self):
        super(ProtoLayer, self).__init__()

    def forward(
        self,
        query_feat,
        support_feat,
        way_num,
        shot_num,
        query_num,
        mode ,
    ):
        t, wq, c = query_feat.size()
        _, ws, _ = support_feat.size()

        # t, wq, c
        query_feat = query_feat.view(t, way_num * query_num, c)
        # t, w, c
        support_feat = support_feat.view(t, way_num, shot_num, c)
        proto_feat = torch.mean(support_feat, dim=2)

        return {
            # t, wq, 1, c - t, 1, w, c -> t, wq, w
            "euclidean": lambda x, y: -torch.sum(
                torch.pow(x.unsqueeze(2) - y.unsqueeze(1), 2),
                dim=3,
            ),
            "euclidean_mean": lambda x, y: -torch.mean(
                torch.pow(x.unsqueeze(2) - y.unsqueeze(1), 2),
                dim=3,
            ),
            # t, wq, c - t, c, w -> t, wq, w
            "cos_sim": lambda x, y: torch.matmul(
                F.normalize(x, p=2, dim=-1),
                torch.transpose(F.normalize(y, p=2, dim=-1), -1, -2)
                # FEAT did not normalize the query_feat
            )*10,
        }[mode](query_feat, proto_feat)


class YccProtoNet(MetricModel):
    def __init__(self, **kwargs):
        super(YccProtoNet, self).__init__(**kwargs)
        self.proto_layer = ProtoLayer()
        self.loss_func = nn.CrossEntropyLoss()
        self.dist = "euclidean" if ("dist" not in kwargs or kwargs["dist"] is None) else kwargs["dist"]

    def set_forward(self, batch):
        """

        :param batch:
        :return:
        """
        image, global_target = batch
        image = image.to(self.device)
        episode_size = image.size(0) // (self.way_num * (self.shot_num + self.query_num))
        feat = self.emb_func(image)
        if len(feat.shape) ==4:
            feat = nn.AdaptiveMaxPool2d(1)(feat)
        support_feat, query_feat, support_target, query_target = self.split_by_episode(feat, mode=1)

        output = self.proto_layer(
            query_feat, support_feat, self.way_num, self.shot_num, self.query_num,self.dist
        ).view(episode_size * self.way_num * self.query_num, self.way_num)
        acc = accuracy(output, query_target.view(-1))

        return output, acc

    def set_forward_loss(self, batch):
        """

        :param batch:
        :return:
        """
        images, global_targets = batch
        images = images.to(self.device)
        episode_size = images.size(0) // (self.way_num * (self.shot_num + self.query_num))
        emb = self.emb_func(images)
        if len(emb.shape) ==4:
            emb = nn.AdaptiveMaxPool2d(1)(emb)
        support_feat, query_feat, support_target, query_target = self.split_by_episode(emb, mode=1)

        output = self.proto_layer(
            query_feat, support_feat, self.way_num, self.shot_num, self.query_num,self.dist
        ).view(episode_size * self.way_num * self.query_num, self.way_num)
        loss = self.loss_func(output, query_target.view(-1))
        acc = accuracy(output, query_target.view(-1))

        return output, acc, loss
